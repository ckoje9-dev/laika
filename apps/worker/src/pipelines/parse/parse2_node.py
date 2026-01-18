"""DXF 2차 파싱: raw DB 조회 + rule-based 정제 + semantic DB 적재."""
from __future__ import annotations

import logging
import math
import json
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src import models
from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)


DEFAULT_RULES = [
    {"kind": "border", "keys": ["BORD", "TITLE", "FORM"], "source": "layer"},
    {"kind": "dimension", "keys": ["DIM"], "source": "layer"},
    {"kind": "symbol", "keys": ["SYM"], "source": "layer"},
    {"kind": "text", "keys": ["TXT", "TEXT"], "source": "layer"},
    {"kind": "axis", "keys": ["AXIS", "GRID"], "source": "layer"},
    {"kind": "column", "keys": ["COL"], "source": "layer"},
    {"kind": "steel_column", "keys": ["STL"], "source": "layer"},
    {"kind": "concrete", "keys": ["CON"], "source": "layer"},
    {"kind": "wall", "keys": ["WAL"], "source": "layer"},
    {"kind": "door", "keys": ["DOOR"], "source": "layer"},
    {"kind": "window", "keys": ["WIN"], "source": "layer"},
    {"kind": "stair", "keys": ["STR"], "source": "layer"},
    {"kind": "elevator", "keys": ["ELV"], "source": "layer"},
    {"kind": "furniture", "keys": ["FURN"], "source": "layer"},
    {"kind": "finish", "keys": ["FIN"], "source": "layer"},
    {"kind": "block", "keys": ["BLOCK"], "source": "type"},
]

SELECTION_RULE_MAP = {
    "basic-border-block": ("border", "block"),
    "basic-dim-layer": ("dimension", "layer"),
    "basic-symbol-layer": ("symbol", "layer"),
    "basic-text-layer": ("text", "layer"),
    "struct-axis-layer": ("axis", "layer"),
    "struct-ccol-layer": ("column", "layer"),
    "struct-scol-layer": ("steel_column", "layer"),
    "struct-cwall-layer": ("concrete", "layer"),
    "non-wall-layer": ("wall", "layer"),
    "non-door-layer": ("door", "layer"),
    "non-window-layer": ("window", "layer"),
    "non-stair-layer": ("stair", "layer"),
    "non-elevator-layer": ("elevator", "layer"),
    "non-furniture-layer": ("furniture", "layer"),
    "non-finish-layer": ("finish", "layer"),
}


def _extract_layer_names(tables: dict[str, Any] | None, entities: list[dict[str, Any]]) -> list[str]:
    layers: list[str] = []
    if isinstance(tables, dict):
        layer_dict = tables.get("layer", {}).get("layers") if isinstance(tables.get("layer"), dict) else None
        if isinstance(layer_dict, dict):
            layers = [k for k in layer_dict.keys() if k]
    if not layers:
        seen = set()
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            name = ent.get("layer") or ent.get("layerName")
            if name and name not in seen:
                seen.add(name)
                layers.append(str(name))
    return layers


def _match_rule(entity: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    layer = str(entity.get("layer") or entity.get("layerName") or "").upper()
    dtype = str(entity.get("type") or "").upper()
    name = str(entity.get("name") or entity.get("block") or entity.get("block_name") or "").upper()
    for rule in rules:
        keys = rule.get("keys") or []
        src = rule["source"]
        match = rule.get("match", "contains")
        if src == "layer":
            if match == "exact" and layer in keys:
                return rule["kind"], f"layer:{layer}"
            if match != "exact" and any(k in layer for k in keys):
                return rule["kind"], f"layer:{layer}"
        if src == "type":
            if match == "exact" and dtype in keys:
                return rule["kind"], f"type:{dtype}"
            if match != "exact" and any(k in dtype for k in keys):
                return rule["kind"], f"type:{dtype}"
        if src == "block":
            if match == "exact" and name in keys:
                return rule["kind"], f"block:{name}"
            if match != "exact" and any(k in name for k in keys):
                return rule["kind"], f"block:{name}"
    return None, None


def _build_semantic_records(
    entities: Iterable[dict[str, Any]],
    file_id: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        kind, source_rule = _match_rule(ent, rules)
        if not kind:
            continue
        records.append(
            {
                "file_id": file_id,
                "kind": kind,
                "confidence": None,
                "source_rule": source_rule,
                "properties": ent,
            }
        )
    return records


def _rules_from_selections(selections: dict[str, list[str]] | None) -> list[dict[str, Any]]:
    if not selections:
        return []
    rules: list[dict[str, Any]] = []
    for key, values in selections.items():
        if key not in SELECTION_RULE_MAP:
            continue
        kind, source = SELECTION_RULE_MAP[key]
        if not values:
            continue
        keys = [str(v).upper() for v in values if v]
        if not keys:
            continue
        rules.append({"kind": kind, "keys": keys, "source": source, "match": "exact"})
    return rules


def _extract_points(entity: dict[str, Any]) -> list[tuple[float, float]]:
    dtype = entity.get("type")
    if dtype == "LINE":
        verts = entity.get("vertices")
        if isinstance(verts, list) and len(verts) >= 2:
            pts = []
            for v in verts:
                if not isinstance(v, dict):
                    continue
                x = v.get("x")
                y = v.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    pts.append((float(x), float(y)))
            if len(pts) >= 2:
                return pts
        sp = entity.get("startPoint") or entity.get("start") or entity.get("start_point")
        ep = entity.get("endPoint") or entity.get("end") or entity.get("end_point")
        if isinstance(sp, dict) and isinstance(ep, dict):
            return [(float(sp.get("x", 0)), float(sp.get("y", 0))), (float(ep.get("x", 0)), float(ep.get("y", 0)))]
    if dtype == "LWPOLYLINE":
        verts = entity.get("vertices")
        if isinstance(verts, list):
            pts = []
            for v in verts:
                if not isinstance(v, dict):
                    continue
                x = v.get("x")
                y = v.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    pts.append((float(x), float(y)))
            return pts
    return []


def _points_inside_bbox(points: list[tuple[float, float]], bbox: dict[str, float]) -> bool:
    for x, y in points:
        if x < bbox["xmin"] or x > bbox["xmax"] or y < bbox["ymin"] or y > bbox["ymax"]:
            return False
    return True


def _axis_orientation(points: list[tuple[float, float]], eps: float = 1e-6) -> tuple[str, float] | None:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if not xs or not ys:
        return None
    if max(xs) - min(xs) < eps:
        return "Y_AXIS", sum(xs) / len(xs)
    if max(ys) - min(ys) < eps:
        return "X_AXIS", sum(ys) / len(ys)
    return None


def _block_bbox_from_entities(block_entities: list[dict[str, Any]]) -> dict[str, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for ent in block_entities:
        if not isinstance(ent, dict):
            continue
        verts = ent.get("vertices")
        if not isinstance(verts, list):
            continue
        for v in verts:
            if not isinstance(v, dict):
                continue
            x = v.get("x")
            y = v.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                xs.append(float(x))
                ys.append(float(y))
    if not xs or not ys:
        return None
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
    }


def _transform_bbox(bbox: dict[str, float], insert: dict[str, Any]) -> dict[str, float]:
    tx = (insert.get("position") or {}).get("x", 0) if isinstance(insert.get("position"), dict) else insert.get("x", 0)
    ty = (insert.get("position") or {}).get("y", 0) if isinstance(insert.get("position"), dict) else insert.get("y", 0)
    sx = insert.get("xScale") or 1
    sy = insert.get("yScale") or 1
    rot = insert.get("rotation") or 0
    theta = math.radians(rot)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    corners = [
        (bbox["min_x"], bbox["min_y"]),
        (bbox["max_x"], bbox["min_y"]),
        (bbox["max_x"], bbox["max_y"]),
        (bbox["min_x"], bbox["max_y"]),
    ]
    world_points: list[tuple[float, float]] = []
    for x, y in corners:
        xs = x * sx
        ys = y * sy
        xr = xs * cos_t - ys * sin_t
        yr = xs * sin_t + ys * cos_t
        xw = xr + tx
        yw = yr + ty
        world_points.append((xw, yw))

    xs = [p[0] for p in world_points]
    ys = [p[1] for p in world_points]
    return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}


def _build_border_records(
    file_id: str,
    blocks: dict[str, Any],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    if not selections:
        return []
    selected = selections.get("basic-border-block") or []
    if not selected:
        return []
    block_name = str(selected[0])
    block_key = block_name
    if isinstance(blocks, dict) and block_name not in blocks:
        for k in blocks.keys():
            if str(k).upper() == block_name.upper():
                block_key = k
                break
    block_def = blocks.get(block_key) if isinstance(blocks, dict) else None
    if not isinstance(block_def, dict):
        return []
    block_entities = block_def.get("entities")
    if not isinstance(block_entities, list):
        return []
    base_bbox = _block_bbox_from_entities(block_entities)
    if not base_bbox:
        return []

    records: list[dict[str, Any]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") != "INSERT":
            continue
        if str(ent.get("name") or "").upper() != block_name.upper():
            continue
        world_bbox = _transform_bbox(base_bbox, ent)
        records.append(
            {
                "file_id": file_id,
                "kind": "border",
                "confidence": None,
                "source_rule": f"block:{block_key}",
                "properties": {
                    "block_name": block_key,
                    "insert_handle": ent.get("handle"),
                    "bbox_local": base_bbox,
                    "bbox_world": world_bbox,
                },
            }
        )
    return records


def _build_axis_summary_records(
    file_id: str,
    borders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    if not selections:
        return []
    axis_layers = selections.get("struct-axis-layer") or []
    axis_layers_upper = {str(v).upper() for v in axis_layers if v}
    if not axis_layers_upper:
        return []

    summaries: list[dict[str, Any]] = []
    for idx, border in enumerate(borders, start=1):
        bbox = border.get("properties", {}).get("bbox_world")
        if not isinstance(bbox, dict):
            continue
        x_axes: list[dict[str, Any]] = []
        y_axes: list[dict[str, Any]] = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if ent.get("type") not in ("LINE", "LWPOLYLINE"):
                continue
            layer = str(ent.get("layer") or ent.get("layerName") or "").upper()
            if layer not in axis_layers_upper:
                continue
            points = _extract_points(ent)
            if not points:
                continue
            if not _points_inside_bbox(points, bbox):
                continue
            axis = _axis_orientation(points)
            if not axis:
                continue
            axis_type, coord = axis
            item = {
                "handle": ent.get("handle"),
                "layer": ent.get("layer") or ent.get("layerName"),
                "coord": coord,
            }
            if axis_type == "X_AXIS":
                x_axes.append(item)
            else:
                y_axes.append(item)

        x_axes.sort(key=lambda x: x["coord"])
        y_axes.sort(key=lambda x: x["coord"])
        for i, item in enumerate(x_axes, start=1):
            item["label"] = f"Y{i}"
        for i, item in enumerate(y_axes, start=1):
            item["label"] = f"X{i}"
        x_spacing = [x_axes[i]["coord"] - x_axes[i - 1]["coord"] for i in range(1, len(x_axes))]
        y_spacing = [y_axes[i]["coord"] - y_axes[i - 1]["coord"] for i in range(1, len(y_axes))]

        summaries.append(
            {
                "file_id": file_id,
                "kind": "axis_summary",
                "confidence": None,
                "source_rule": "layer:struct-axis-layer",
                "properties": {
                    "border_index": idx,
                    "border_handle": border.get("properties", {}).get("insert_handle"),
                    "x_axes": x_axes,
                    "y_axes": y_axes,
                    "x_spacing": x_spacing,
                    "y_spacing": y_spacing,
                },
            }
        )
    return summaries


def _entity_center_and_size(entity: dict[str, Any]) -> tuple[float, float, dict[str, Any]] | None:
    dtype = entity.get("type")
    if dtype == "CIRCLE":
        center = entity.get("center") or entity.get("position")
        if not isinstance(center, dict):
            return None
        r = entity.get("radius")
        if not isinstance(r, (int, float)):
            return None
        return (
            float(center.get("x", 0)),
            float(center.get("y", 0)),
            {"shape": "circle", "radius": float(r), "diameter": float(r) * 2.0},
        )
    if dtype in ("LWPOLYLINE", "POLYLINE"):
        verts = entity.get("vertices")
        if not isinstance(verts, list) or not verts:
            return None
        xs = []
        ys = []
        for v in verts:
            if not isinstance(v, dict):
                continue
            x = v.get("x")
            y = v.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                xs.append(float(x))
                ys.append(float(y))
        if not xs or not ys:
            return None
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        width = max_x - min_x
        height = max_y - min_y
        return (
            (min_x + max_x) / 2.0,
            (min_y + max_y) / 2.0,
            {"shape": "rect", "width": width, "height": height},
        )
    return None


def _axis_intersections(summary: dict[str, Any]) -> list[tuple[float, float]]:
    x_axes = summary.get("x_axes") or []
    y_axes = summary.get("y_axes") or []
    xs = [a.get("coord") for a in y_axes if isinstance(a, dict) and isinstance(a.get("coord"), (int, float))]
    ys = [a.get("coord") for a in x_axes if isinstance(a, dict) and isinstance(a.get("coord"), (int, float))]
    return [(float(x), float(y)) for x in xs for y in ys]


def _match_intersection(center: tuple[float, float], intersections: list[tuple[float, float]], eps: float) -> bool:
    cx, cy = center
    for ix, iy in intersections:
        if abs(cx - ix) <= eps and abs(cy - iy) <= eps:
            return True
    return False


def _assign_column_types(columns: list[dict[str, Any]]) -> None:
    def size_key(item: dict[str, Any]) -> tuple:
        size = item.get("size") or {}
        shape = size.get("shape")
        if shape == "circle":
            r = size.get("radius")
            return ("circle", round(float(r or 0), 2))
        w = size.get("width")
        h = size.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
            a = round(max(w, h), 2)
            b = round(min(w, h), 2)
            return ("rect", a, b)
        return ("unknown", 0)

    unique = {}
    for col in columns:
        key = size_key(col)
        unique.setdefault(key, None)
    ordered = sorted(unique.keys())
    type_map = {key: f"C{i + 1}" for i, key in enumerate(ordered)}
    for col in columns:
        col["column_type"] = type_map[size_key(col)]


def _build_column_records(
    file_id: str,
    axis_summaries: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
    eps: float = 1.0,
) -> list[dict[str, Any]]:
    if not selections:
        return []
    layer_names = selections.get("struct-ccol-layer") or []
    layer_set = {str(v).upper() for v in layer_names if v}
    if not layer_set:
        return []

    columns: list[dict[str, Any]] = []
    for summary in axis_summaries:
        bbox = summary.get("bbox")
        intersections = summary.get("intersections") or []
        if not isinstance(bbox, dict):
            continue
        if not intersections:
            continue
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            layer = str(ent.get("layer") or ent.get("layerName") or "").upper()
            if layer not in layer_set:
                continue
            center_data = _entity_center_and_size(ent)
            if not center_data:
                continue
            cx, cy, size = center_data
            if not _points_inside_bbox([(cx, cy)], bbox):
                continue
            if not _match_intersection((cx, cy), intersections, eps):
                continue
            columns.append(
                {
                    "file_id": file_id,
                    "border_index": summary.get("border_index"),
                    "center": {"x": cx, "y": cy},
                    "size": size,
                }
            )

    if not columns:
        return []
    _assign_column_types(columns)

    records = []
    for col in columns:
        records.append(
            {
                "file_id": file_id,
                "kind": "concrete_column",
                "confidence": None,
                "source_rule": "layer:struct-ccol-layer",
                "properties": col,
            }
        )
    return records


async def run(
    file_id: Optional[str] = None,
    selections: dict[str, list[str]] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> None:
    """raw DB를 기반으로 rule-based 정제 후 semantic_objects에 저장."""
    if not file_id:
        logger.error("file_id가 없어 2차 파싱을 건너뜁니다.")
        return

    async with SessionLocal() as session:
        section_row = await session.get(models.DxfParseSection, file_id)
        if not section_row:
            logger.error("raw db가 없습니다: file_id=%s", file_id)
            return

        tables = section_row.tables if isinstance(section_row.tables, dict) else {}
        blocks = section_row.blocks if isinstance(section_row.blocks, dict) else {}
        entities = section_row.entities if isinstance(section_row.entities, list) else []
        layers = _extract_layer_names(tables, entities)
        entity_count = len(entities)

        effective_rules = rules or _rules_from_selections(selections) or DEFAULT_RULES
        if selections:
            logger.info(
                "parse2 selections: border=%s axis=%s ccol=%s",
                selections.get("basic-border-block"),
                selections.get("struct-axis-layer"),
                selections.get("struct-ccol-layer"),
            )
            if selections.get("basic-border-block"):
                block_name = str(selections.get("basic-border-block")[0])
                insert_hits = [
                    e for e in entities if isinstance(e, dict) and e.get("type") == "INSERT" and str(e.get("name") or "").upper() == block_name.upper()
                ]
                logger.info("border block=%s blocks=%s inserts=%s", block_name, len(blocks), len(insert_hits))
            if selections.get("struct-axis-layer"):
                axis_layers = {str(v).upper() for v in selections.get("struct-axis-layer") or [] if v}
                axis_hits = [
                    e
                    for e in entities
                    if isinstance(e, dict)
                    and e.get("type") in ("LINE", "LWPOLYLINE")
                    and str(e.get("layer") or e.get("layerName") or "").upper() in axis_layers
                ]
                logger.info("axis layers=%s hits=%s", list(axis_layers), len(axis_hits))
            if selections.get("struct-ccol-layer"):
                col_layers = {str(v).upper() for v in selections.get("struct-ccol-layer") or [] if v}
                col_hits = [
                    e
                    for e in entities
                    if isinstance(e, dict)
                    and str(e.get("layer") or e.get("layerName") or "").upper() in col_layers
                ]
                logger.info("column layers=%s hits=%s", list(col_layers), len(col_hits))
        records = _build_semantic_records(entities, file_id, effective_rules)
        border_records = _build_border_records(file_id, blocks, entities, selections)
        if border_records:
            records.extend(border_records)
        axis_summaries = _build_axis_summary_records(file_id, border_records, entities, selections)
        if axis_summaries:
            records.extend(axis_summaries)
            axis_for_columns = []
            for item in axis_summaries:
                axis_for_columns.append(
                    {
                        "border_index": item["properties"].get("border_index"),
                        "bbox": next(
                            (
                                b.get("properties", {}).get("bbox_world")
                                for b in border_records
                                if b.get("properties", {}).get("insert_handle") == item["properties"].get("border_handle")
                            ),
                            None,
                        ),
                        "intersections": _axis_intersections(item["properties"]),
                    }
                )
            column_records = _build_column_records(file_id, axis_for_columns, entities, selections, eps=1.0)
            if column_records:
                records.extend(column_records)

        try:
            await session.execute(text("delete from semantic_objects where file_id = :file_id"), {"file_id": file_id})
            if records:
                for rec in records:
                    if "properties" not in rec or rec["properties"] is None:
                        rec["properties"] = {}
                    rec["properties"] = json.dumps(rec["properties"], ensure_ascii=False)
                await session.execute(
                    text(
                        """
                        insert into semantic_objects (file_id, kind, confidence, source_rule, properties, created_at)
                        values (:file_id, :kind, :confidence, :source_rule, CAST(:properties AS JSONB), now())
                        """
                    ),
                    records,
                )
            await session.execute(
                text(
                    """
                    update files set
                        layer_count = :layers,
                        entity_count = :entities
                    where id = :file_id
                    """
                ),
                {
                    "layers": len(layers),
                    "entities": entity_count,
                    "file_id": file_id,
                },
            )
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, layer_count, entity_count, message)
                    values (:file_id, 'success', now(), now(), :layers, :entities, :msg)
                    """
                ),
                {
                    "file_id": file_id,
                    "layers": len(layers),
                    "entities": entity_count,
                    "msg": "parse2: rule-based semantic build",
                },
            )
            await session.commit()
            logger.info("2차 파싱 완료: file_id=%s records=%s", file_id, len(records))
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("2차 파싱 DB 저장 실패: %s", exc)
            raise
