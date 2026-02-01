"""Grid axis detection and analysis."""
from typing import Any

from ..geometry import extract_points, points_inside_bbox, axis_orientation, axis_intersections, points_to_wkt_multipoint, bbox_to_wkt_polygon


def build_axis_summary_records(
    file_id: str,
    borders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    """Detect and analyze grid axes within border regions.

    Args:
        file_id: File UUID
        borders: List of detected border records
        entities: List of DXF entities
        selections: User selections

    Returns:
        List of axis_summary semantic records
    """
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

        # Find axis lines within this border
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if ent.get("type") not in ("LINE", "LWPOLYLINE"):
                continue

            layer = str(ent.get("layer") or ent.get("layerName") or "").upper()
            if layer not in axis_layers_upper:
                continue

            points = extract_points(ent)
            if not points:
                continue

            if not points_inside_bbox(points, bbox):
                continue

            axis = axis_orientation(points)
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

        # Sort and label axes
        x_axes.sort(key=lambda x: x["coord"])
        y_axes.sort(key=lambda x: x["coord"])

        for i, item in enumerate(x_axes, start=1):
            item["label"] = f"Y{i}"

        for i, item in enumerate(y_axes, start=1):
            item["label"] = f"X{i}"

        # Compute spacing
        x_spacing = [x_axes[i]["coord"] - x_axes[i - 1]["coord"] for i in range(1, len(x_axes))]
        y_spacing = [y_axes[i]["coord"] - y_axes[i - 1]["coord"] for i in range(1, len(y_axes))]

        # Compute intersections
        intersections = axis_intersections({"x_axes": x_axes, "y_axes": y_axes})

        # Generate WKT for PostGIS (intersections as MULTIPOINT, bbox as POLYGON)
        geom_wkt = points_to_wkt_multipoint(intersections) if intersections else bbox_to_wkt_polygon(bbox)

        summaries.append({
            "file_id": file_id,
            "kind": "axis_summary",
            "confidence": None,
            "source_rule": "layer:struct-axis-layer",
            "geom_wkt": geom_wkt,  # For PostGIS storage
            "properties": {
                "border_index": idx,
                "border_handle": border.get("properties", {}).get("insert_handle"),
                "x_axes": x_axes,
                "y_axes": y_axes,
                "x_spacing": x_spacing,
                "y_spacing": y_spacing,
                "bbox": bbox,
                "intersections": intersections,
            },
        })

    return summaries
