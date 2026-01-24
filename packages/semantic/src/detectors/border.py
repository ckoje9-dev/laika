"""Border (title block) detection."""
from typing import Any

from ..geometry import block_bbox_from_entities, transform_bbox


def build_border_records(
    file_id: str,
    blocks: dict[str, Any],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    """Detect border blocks (title blocks) from INSERT entities.

    Args:
        file_id: File UUID
        blocks: Block definitions dictionary
        entities: List of DXF entities
        selections: User selections

    Returns:
        List of border semantic records
    """
    if not selections:
        return []

    selected = selections.get("basic-border-block") or []
    if not selected:
        return []

    block_name = str(selected[0])
    block_key = block_name

    # Find block definition (case-insensitive)
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

    # Compute local bounding box
    base_bbox = block_bbox_from_entities(block_entities)
    if not base_bbox:
        return []

    # Find all INSERT entities matching this block
    records: list[dict[str, Any]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") != "INSERT":
            continue
        if str(ent.get("name") or "").upper() != block_name.upper():
            continue

        # Transform to world coordinates
        world_bbox = transform_bbox(base_bbox, ent)

        records.append({
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
        })

    return records
