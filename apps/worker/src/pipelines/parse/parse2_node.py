"""DXF 2차 파싱: raw DB 조회 + rule-based 정제 + semantic DB 적재."""
from __future__ import annotations

import logging
import math
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


def _match_rule(entity: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[str, str]:
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
    return dtype.lower() if dtype else "unknown", "type:unknown"


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
        records = _build_semantic_records(entities, file_id, effective_rules)
        border_records = _build_border_records(file_id, blocks, entities, selections)
        if border_records:
            records.extend(border_records)

        try:
            await session.execute(text("delete from semantic_objects where file_id = :file_id"), {"file_id": file_id})
            if records:
                await session.execute(
                    text(
                        """
                        insert into semantic_objects (file_id, kind, confidence, source_rule, properties, created_at)
                        values (:file_id, :kind, :confidence, :source_rule, :properties, now())
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
