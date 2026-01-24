"""Column detection at grid intersections."""
from typing import Any

from ..geometry import entity_center_and_size, points_inside_bbox, match_intersection


def assign_column_types(columns: list[dict[str, Any]]) -> None:
    """Assign column type labels (C1, C2, ...) based on size grouping.

    Args:
        columns: List of column dictionaries (modified in-place)
    """
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

    # Group by size
    unique = {}
    for col in columns:
        key = size_key(col)
        unique.setdefault(key, None)

    # Assign type labels
    ordered = sorted(unique.keys())
    type_map = {key: f"C{i + 1}" for i, key in enumerate(ordered)}

    for col in columns:
        col["column_type"] = type_map[size_key(col)]


def build_column_records(
    file_id: str,
    axis_summaries: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
    eps: float = 150.0,
) -> list[dict[str, Any]]:
    """Detect columns at grid axis intersections.

    Args:
        file_id: File UUID
        axis_summaries: List of axis summary records
        entities: List of DXF entities
        selections: User selections
        eps: Distance tolerance for intersection matching

    Returns:
        List of concrete_column semantic records
    """
    if not selections:
        return []

    layer_names = selections.get("struct-ccol-layer") or []
    layer_set = {str(v).upper() for v in layer_names if v}
    if not layer_set:
        return []

    columns: list[dict[str, Any]] = []

    for summary in axis_summaries:
        props = summary.get("properties", {})
        bbox = props.get("bbox")
        intersections = props.get("intersections") or []

        if not isinstance(bbox, dict):
            continue
        if not intersections:
            continue

        # Find column entities within this border
        for ent in entities:
            if not isinstance(ent, dict):
                continue

            layer = str(ent.get("layer") or ent.get("layerName") or "").upper()
            if layer not in layer_set:
                continue

            center_data = entity_center_and_size(ent)
            if not center_data:
                continue

            cx, cy, size = center_data

            # Check if inside border
            if not points_inside_bbox([(cx, cy)], bbox):
                continue

            # Check if at intersection
            if not match_intersection((cx, cy), intersections, eps):
                continue

            columns.append({
                "file_id": file_id,
                "border_index": props.get("border_index"),
                "center": {"x": cx, "y": cy},
                "size": size,
            })

    if not columns:
        return []

    # Assign type labels
    assign_column_types(columns)

    # Convert to semantic records
    records = []
    for col in columns:
        records.append({
            "file_id": file_id,
            "kind": "concrete_column",
            "confidence": None,
            "source_rule": "layer:struct-ccol-layer",
            "properties": col,
        })

    return records
