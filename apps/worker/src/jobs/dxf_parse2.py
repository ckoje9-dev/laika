"""DXF 2차 파싱/정규화 잡: 룰 기반으로 엔티티 속성 갱신."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select, update, text, func
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src.session import SessionLocal
from packages.db.src import models

logger = logging.getLogger(__name__)

DXF_RULES_PATH = Path(os.getenv("DXF_RULES_PATH", "config/dxf_rules.json"))
STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
GRID_TOL = 1e-3


def _load_rules() -> dict[str, Any]:
    if not DXF_RULES_PATH.exists():
        logger.warning("DXF 룰 파일을 찾을 수 없습니다: %s", DXF_RULES_PATH)
        return {}
    try:
        with DXF_RULES_PATH.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as e:  # pragma: no cover
        logger.warning("DXF 룰 파일 로드 실패: %s", e)
        return {}


def _classify_layer(layer: str | None, color_index: int | None, rules: list[dict[str, Any]]) -> str | None:
    if not layer or not rules:
        return None
    lname = layer.lower()
    for rule in rules:
        contains = rule.get("contains") or []
        color = rule.get("color")
        if any(key in lname for key in contains) and (color is None or color == color_index):
            return rule.get("tag")
    return None


def _match_layer_definition(layer: str | None, color_index: int | None, defs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not layer or not defs:
        return None
    for item in defs:
        name = item.get("name")
        if not name or name.lower() != layer.lower():
            continue
        color = item.get("color")
        if color is not None and color_index is not None and int(color) != int(color_index):
            continue
        return {"name": name, "color": color, "description": item.get("description")}
    return None


def _parse_point_wkt(wkt: str | None) -> tuple[float, float] | None:
    if not wkt or not wkt.startswith("POINT"):
        return None
    try:
        coords = wkt[wkt.index("(") + 1 : wkt.index(")")].split()
        return float(coords[0]), float(coords[1])
    except Exception:
        return None


def _parse_linestring_wkt(wkt: str | None) -> list[tuple[float, float]]:
    if not wkt or not wkt.startswith("LINESTRING"):
        return []
    try:
        coord_str = wkt[wkt.index("(") + 1 : wkt.rindex(")")]
        pts = []
        for pair in coord_str.split(","):
            x, y = pair.strip().split()[:2]
            pts.append((float(x), float(y)))
        return pts
    except Exception:
        return []


def _bbox_from_points(pts: Iterable[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _contains_point(bbox: tuple[float, float, float, float], pt: tuple[float, float]) -> bool:
    minx, miny, maxx, maxy = bbox
    x, y = pt
    return minx <= x <= maxx and miny <= y <= maxy


def _unique_sorted(values: list[float], tol: float = GRID_TOL) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    clusters: list[float] = [values[0]]
    for v in values[1:]:
        if abs(v - clusters[-1]) <= tol:
            clusters[-1] = (clusters[-1] + v) / 2
        else:
            clusters.append(v)
    return clusters


def _segments_from_linestring(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    segs = []
    for i in range(len(points) - 1):
        segs.append((points[i], points[i + 1]))
    return segs


async def run(file_id: str | None = None) -> None:
    """룰 기반 2차 파싱: 레이어 규칙 등을 적용해 properties.classification을 갱신."""
    if not file_id:
        logger.error("file_id가 필요합니다.")
        return

    rules = _load_rules()
    layer_defs = rules.get("layer_definitions") or []

    async with SessionLocal() as session:
        try:
            file_row = await session.get(models.File, file_id)
            stmt = select(
                models.DxfEntityRaw.id,
                models.DxfEntityRaw.type,
                models.DxfEntityRaw.layer,
                models.DxfEntityRaw.properties,
                func.ST_AsText(models.DxfEntityRaw.geom),
            ).where(models.DxfEntityRaw.file_id == file_id)
            rows = await session.execute(stmt)
            rows = rows.all()
            if not rows:
                logger.warning("엔티티가 없습니다. file_id=%s", file_id)
                return

            # 1) properties 갱신 (layer 정의)
            for rid, _, layer, props, _geom_wkt in rows:
                props = props or {}
                layer_def = _match_layer_definition(layer, props.get("color_index"), layer_defs) if layer_defs else None
                if layer_def:
                    props["layer_definition"] = layer_def
                await session.execute(
                    update(models.DxfEntityRaw)
                    .where(models.DxfEntityRaw.id == rid)
                    .values(properties=props)
                )

            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, message)
                    values (:file_id, 'success', now(), now(), 'parse2')
                    """
                ),
                {"file_id": file_id},
            )
            await session.commit()
            logger.info("2차 파싱 완료: file_id=%s (entities=%s)", file_id, len(rows))

            # 2) 표 추출: 수평/수직 선분 그리드와 텍스트를 이용해 셀 구성
            verticals: list[float] = []
            horizontals: list[float] = []
            text_points: list[dict[str, Any]] = []

            for rid, dtype, layer, props, geom_wkt in rows:
                if dtype == "LINE":
                    pts = _parse_linestring_wkt(geom_wkt)
                    if len(pts) == 2:
                        (x1, y1), (x2, y2) = pts
                        if abs(x1 - x2) <= GRID_TOL:
                            verticals.append((x1 + x2) / 2)
                        if abs(y1 - y2) <= GRID_TOL:
                            horizontals.append((y1 + y2) / 2)
                elif dtype in ("LWPOLYLINE", "POLYLINE"):
                    pts = _parse_linestring_wkt(geom_wkt)
                    for s in _segments_from_linestring(pts):
                        (x1, y1), (x2, y2) = s
                        if abs(x1 - x2) <= GRID_TOL:
                            verticals.append((x1 + x2) / 2)
                        if abs(y1 - y2) <= GRID_TOL:
                            horizontals.append((y1 + y2) / 2)
                elif dtype in ("TEXT", "MTEXT"):
                    pt = _parse_point_wkt(geom_wkt)
                    if pt:
                        text_points.append(
                            {
                                "id": rid,
                                "layer": layer,
                                "point": pt,
                                "text": props.get("text") or props.get("value"),
                            }
                        )

            xs = _unique_sorted(verticals)
            ys = _unique_sorted(horizontals)

            tables = []
            cells = []
            for r in range(len(ys) - 1):
                for c in range(len(xs) - 1):
                    bbox = (xs[c], ys[r], xs[c + 1], ys[r + 1])
                    cell_texts = [t for t in text_points if _contains_point(bbox, t["point"])]
                    if not cell_texts:
                        continue
                    cells.append({"row": r, "col": c, "bbox": bbox, "texts": cell_texts})

            if cells:
                tables.append({"grid_x": xs, "grid_y": ys, "cells": cells})
            # 폴백: 그리드가 없을 때 닫힌 폴리라인을 테이블 경계로 보고 내부 텍스트를 단일 셀로 묶음
            if not tables:
                for rid, dtype, layer, props, geom_wkt in rows:
                    if dtype in ("LWPOLYLINE", "POLYLINE"):
                        pts = _parse_linestring_wkt(geom_wkt)
                        if len(pts) >= 4 and pts[0] == pts[-1]:
                            bbox = _bbox_from_points(pts)
                            if not bbox:
                                continue
                            cell_texts = [t for t in text_points if _contains_point(bbox, t["point"])]
                            if cell_texts:
                                tables.append(
                                    {
                                        "boundary_id": rid,
                                        "layer": layer,
                                        "cells": [
                                            {
                                                "row": 0,
                                                "col": 0,
                                                "bbox": bbox,
                                                "texts": cell_texts,
                                            }
                                        ],
                                    }
                                )

            if file_row:
                stem = Path(file_row.path_dxf).stem if file_row.path_dxf else file_id
            else:
                stem = file_id
            table_path = STORAGE_DERIVED_PATH / f"{stem}_tables.json"
            try:
                STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)
                with table_path.open("w", encoding="utf-8") as fp:
                    json.dump(tables, fp, ensure_ascii=False, indent=2)
                logger.info("테이블 추출 완료: %s (tables=%s)", table_path, len(tables))
            except Exception as e:  # pragma: no cover
                logger.warning("테이블 저장 실패: %s", e)
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("2차 파싱 중 오류: %s", e)
            raise
