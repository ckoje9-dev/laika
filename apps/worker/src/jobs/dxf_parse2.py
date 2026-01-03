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
AXIS_LAYER = "A-CEN1"
AXIS_CLUSTER_TOL = 5.0
STRUCTURE_PATH_SUFFIX = "_structure.json"
AXES_PATH_SUFFIX = "_axes.json"


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


def _assign_index(values: list[float], tol: float = 1e-2) -> tuple[list[float], dict[float, int]]:
    """좌표값을 tol 기준으로 클러스터링하여 정렬된 고유값과 매핑을 반환."""
    uniq = _unique_sorted(values, tol)
    mapping: dict[float, int] = {}
    for v in values:
        for idx, u in enumerate(uniq):
            if abs(v - u) <= tol:
                mapping[v] = idx
                break
    return uniq, mapping


def _poly_area_bbox(points: list[tuple[float, float]]) -> tuple[float | None, tuple[float, float, float, float] | None]:
    """단순 다각형 면적과 bbox를 계산."""
    if len(points) < 3:
        return None, _bbox_from_points(points)
    area = 0.0
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    return area, _bbox_from_points(points)


def _extract_axes(rows: list[tuple], tol: float = AXIS_CLUSTER_TOL) -> dict[str, Any]:
    """A-CEN1 레이어의 수평/수직 축선을 모으고 클러스터링."""
    xs: list[float] = []
    ys: list[float] = []
    axis_entities: list[int] = []

    for rid, dtype, layer, _props, geom_wkt in rows:
        if layer != AXIS_LAYER:
            continue
        if dtype == "LINE":
            pts = _parse_linestring_wkt(geom_wkt)
            if len(pts) == 2:
                (x1, y1), (x2, y2) = pts
                if abs(x1 - x2) <= GRID_TOL:
                    xs.append((x1 + x2) / 2)
                if abs(y1 - y2) <= GRID_TOL:
                    ys.append((y1 + y2) / 2)
                axis_entities.append(rid)
        elif dtype in ("LWPOLYLINE", "POLYLINE"):
            pts = _parse_linestring_wkt(geom_wkt)
            for (x1, y1), (x2, y2) in _segments_from_linestring(pts):
                if abs(x1 - x2) <= GRID_TOL:
                    xs.append((x1 + x2) / 2)
                if abs(y1 - y2) <= GRID_TOL:
                    ys.append((y1 + y2) / 2)
            axis_entities.append(rid)

    x_unique = _unique_sorted(xs, tol)
    y_unique = _unique_sorted(ys, tol)

    def _spacing(values: list[float]) -> list[float]:
        if len(values) < 2:
            return []
        return [round(values[i + 1] - values[i], 3) for i in range(len(values) - 1)]

    return {
        "layer": AXIS_LAYER,
        "x_axes": x_unique,
        "y_axes": y_unique,
        "x_spacing": _spacing(x_unique),
        "y_spacing": _spacing(y_unique),
        "entity_ids": axis_entities,
    }


def _collect_structure(rows: list[tuple], axes: dict[str, Any]) -> dict[str, Any]:
    """레이어 기반으로 구조요소 분류."""
    concrete_columns: list[dict[str, Any]] = []
    steel_columns: list[dict[str, Any]] = []
    walls: list[dict[str, Any]] = []
    slabs: list[dict[str, Any]] = []
    openings: list[dict[str, Any]] = []

    for rid, dtype, layer, props, geom_wkt in rows:
        pts = _parse_linestring_wkt(geom_wkt) if geom_wkt and geom_wkt.startswith("LINESTRING") else []
        area, bbox = _poly_area_bbox(pts) if pts else (None, None)

        if layer == "A-COL":
            if dtype == "CIRCLE":
                center = props.get("center") or _parse_point_wkt(geom_wkt)
                concrete_columns.append({"id": rid, "type": dtype, "center": center, "area": props.get("area"), "bbox": bbox})
            elif dtype in ("LWPOLYLINE", "POLYLINE"):
                concrete_columns.append({"id": rid, "type": dtype, "bbox": bbox, "area": area, "vertices": pts})
        elif layer == "A-STL":
            if dtype in ("LWPOLYLINE", "POLYLINE", "CIRCLE"):
                steel_columns.append({"id": rid, "type": dtype, "bbox": bbox, "area": area, "vertices": pts})
        elif layer == "A-CON":
            if dtype in ("LWPOLYLINE", "POLYLINE"):
                is_closed = bool(pts) and (pts[0] == pts[-1])
                target = slabs if (is_closed and area and area > 0) else walls
                target.append({"id": rid, "type": dtype, "bbox": bbox, "area": area, "is_closed": is_closed, "vertices": pts})
        elif layer == "A-OPEN1":
            openings.append({"id": rid, "type": dtype, "bbox": bbox, "geom": geom_wkt})

    # 슬래브 중 최대 면적을 대표 슬래브로 표시
    slab_main_id = None
    if slabs:
        slab_main_id = max(slabs, key=lambda s: s.get("area") or 0).get("id")
    return {
        "axes_used": {"x_axes": axes.get("x_axes"), "y_axes": axes.get("y_axes"), "layer": axes.get("layer")},
        "concrete_columns": concrete_columns,
        "steel_columns": steel_columns,
        "walls": walls,
        "slabs": slabs,
        "main_slab_id": slab_main_id,
        "openings": openings,
    }


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
            axes = _extract_axes(rows)
            axes_path = None
            structure_path = None
            structure = _collect_structure(rows, axes)
            if file_row and file_row.path_dxf:
                stem = Path(file_row.path_dxf).stem
                axes_path = STORAGE_DERIVED_PATH / f"{stem}{AXES_PATH_SUFFIX}"
                structure_path = STORAGE_DERIVED_PATH / f"{stem}{STRUCTURE_PATH_SUFFIX}"
                axes_path.parent.mkdir(parents=True, exist_ok=True)
                with axes_path.open("w", encoding="utf-8") as fp:
                    json.dump(axes, fp, ensure_ascii=False, indent=2)
                with structure_path.open("w", encoding="utf-8") as fp:
                    json.dump(structure, fp, ensure_ascii=False, indent=2)
                logger.info("축선 정보 저장: %s", axes_path)
                logger.info("구조 정보 저장: %s", structure_path)

            logger.info(
                "2차 파싱 완료: file_id=%s (entities=%s, axes=%s, structure_cols=%s walls=%s slabs=%s)",
                file_id,
                len(rows),
                len(axes.get("entity_ids", [])),
                len(structure.get("concrete_columns", [])) if structure else 0,
                len(structure.get("walls", [])) if structure else 0,
                len(structure.get("slabs", [])) if structure else 0,
            )
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("2차 파싱 중 오류: %s", e)
            raise
