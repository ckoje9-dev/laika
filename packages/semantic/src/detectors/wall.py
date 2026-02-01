"""Wall detection from parallel line pairs."""
import math
from typing import Any

from ..geometry import extract_points, points_inside_bbox


def _line_direction(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    """Compute normalized direction vector from p1 to p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _line_length(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Compute distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


def _are_parallel(dir1: tuple[float, float], dir2: tuple[float, float], angle_tol: float = 0.05) -> bool:
    """Check if two direction vectors are parallel (same or opposite direction).

    Args:
        dir1: First normalized direction vector
        dir2: Second normalized direction vector
        angle_tol: Tolerance for dot product (default ~3 degrees)

    Returns:
        True if vectors are parallel
    """
    dot = abs(dir1[0] * dir2[0] + dir1[1] * dir2[1])
    return dot > (1.0 - angle_tol)


def _perpendicular_distance(
    line1_start: tuple[float, float],
    line1_end: tuple[float, float],
    line2_start: tuple[float, float],
    line2_end: tuple[float, float],
) -> float:
    """Compute perpendicular distance between two parallel lines.

    Uses the formula: distance = |cross product| / |direction|
    """
    # Direction of line1
    dx = line1_end[0] - line1_start[0]
    dy = line1_end[1] - line1_start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return float('inf')

    # Vector from line1_start to line2_start
    vx = line2_start[0] - line1_start[0]
    vy = line2_start[1] - line1_start[1]

    # Cross product gives perpendicular distance * length
    cross = abs(dx * vy - dy * vx)
    return cross / length


def _lines_overlap(
    line1_start: tuple[float, float],
    line1_end: tuple[float, float],
    line2_start: tuple[float, float],
    line2_end: tuple[float, float],
    min_overlap_ratio: float = 0.3,
) -> bool:
    """Check if two parallel lines have sufficient overlap.

    Projects both lines onto their common direction and checks overlap.
    """
    # Get direction from line1
    dx = line1_end[0] - line1_start[0]
    dy = line1_end[1] - line1_start[1]
    length1 = math.sqrt(dx * dx + dy * dy)
    if length1 < 1e-9:
        return False

    # Normalize direction
    ux, uy = dx / length1, dy / length1

    # Project all points onto this direction
    def project(p: tuple[float, float]) -> float:
        return p[0] * ux + p[1] * uy

    t1_start = project(line1_start)
    t1_end = project(line1_end)
    t2_start = project(line2_start)
    t2_end = project(line2_end)

    # Ensure start < end for each line
    if t1_start > t1_end:
        t1_start, t1_end = t1_end, t1_start
    if t2_start > t2_end:
        t2_start, t2_end = t2_end, t2_start

    # Compute overlap
    overlap_start = max(t1_start, t2_start)
    overlap_end = min(t1_end, t2_end)
    overlap = max(0, overlap_end - overlap_start)

    # Check if overlap is sufficient relative to shorter line
    shorter_length = min(t1_end - t1_start, t2_end - t2_start)
    if shorter_length < 1e-9:
        return False

    return overlap / shorter_length >= min_overlap_ratio


def _compute_wall_geometry(
    line1_start: tuple[float, float],
    line1_end: tuple[float, float],
    line2_start: tuple[float, float],
    line2_end: tuple[float, float],
) -> dict[str, Any]:
    """Compute wall geometry from two parallel lines.

    Returns:
        Dictionary with: thickness, length, start_midpoint, end_midpoint, direction
    """
    thickness = _perpendicular_distance(line1_start, line1_end, line2_start, line2_end)

    # Get direction from line1
    dx = line1_end[0] - line1_start[0]
    dy = line1_end[1] - line1_start[1]
    length1 = math.sqrt(dx * dx + dy * dy)
    if length1 < 1e-9:
        return {}

    ux, uy = dx / length1, dy / length1

    # Project all points onto this direction
    def project(p: tuple[float, float]) -> float:
        return p[0] * ux + p[1] * uy

    t1_start = project(line1_start)
    t1_end = project(line1_end)
    t2_start = project(line2_start)
    t2_end = project(line2_end)

    # Find overlap region
    if t1_start > t1_end:
        t1_start, t1_end = t1_end, t1_start
        line1_start, line1_end = line1_end, line1_start
    if t2_start > t2_end:
        t2_start, t2_end = t2_end, t2_start
        line2_start, line2_end = line2_end, line2_start

    # Wall start is at max of both starts, wall end is at min of both ends
    wall_t_start = max(t1_start, t2_start)
    wall_t_end = min(t1_end, t2_end)
    wall_length = wall_t_end - wall_t_start

    if wall_length <= 0:
        return {}

    # Find points on each line at wall start/end positions
    # For line1
    def point_at_t(start: tuple[float, float], end: tuple[float, float], t: float, t_start: float, t_end: float) -> tuple[float, float]:
        if abs(t_end - t_start) < 1e-9:
            return start
        ratio = (t - t_start) / (t_end - t_start)
        return (
            start[0] + ratio * (end[0] - start[0]),
            start[1] + ratio * (end[1] - start[1]),
        )

    p1_at_start = point_at_t(line1_start, line1_end, wall_t_start, t1_start, t1_end)
    p1_at_end = point_at_t(line1_start, line1_end, wall_t_end, t1_start, t1_end)
    p2_at_start = point_at_t(line2_start, line2_end, wall_t_start, t2_start, t2_end)
    p2_at_end = point_at_t(line2_start, line2_end, wall_t_end, t2_start, t2_end)

    # Midpoints
    start_midpoint = (
        (p1_at_start[0] + p2_at_start[0]) / 2,
        (p1_at_start[1] + p2_at_start[1]) / 2,
    )
    end_midpoint = (
        (p1_at_end[0] + p2_at_end[0]) / 2,
        (p1_at_end[1] + p2_at_end[1]) / 2,
    )

    return {
        "thickness": round(thickness, 2),
        "length": round(wall_length, 2),
        "start": {"x": round(start_midpoint[0], 2), "y": round(start_midpoint[1], 2)},
        "end": {"x": round(end_midpoint[0], 2), "y": round(end_midpoint[1], 2)},
        "direction": {"x": round(ux, 4), "y": round(uy, 4)},
    }


def _extract_line_data(entity: dict[str, Any]) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    """Extract line segments from LINE or LWPOLYLINE entity.

    Returns:
        List of (start_point, end_point, handle) tuples
    """
    points = extract_points(entity)
    if len(points) < 2:
        return []

    handle = entity.get("handle", "")
    dtype = entity.get("type")

    if dtype == "LINE":
        return [(points[0], points[1], handle)]

    if dtype == "LWPOLYLINE":
        segments = []
        for i in range(len(points) - 1):
            segments.append((points[i], points[i + 1], f"{handle}_{i}"))
        return segments

    return []


def build_wall_records(
    file_id: str,
    borders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
    max_thickness: float = 1000.0,
    min_length: float = 500.0,
) -> list[dict[str, Any]]:
    """Detect walls as parallel line pairs on designated layers.

    Args:
        file_id: File UUID
        borders: List of detected border records (for bbox filtering)
        entities: List of DXF entities
        selections: User selections with wall layer mappings
        max_thickness: Maximum wall thickness in mm (default 1000)
        min_length: Minimum wall length in mm (default 500)

    Returns:
        List of wall semantic records
    """
    if not selections:
        return []

    # Get wall layers from selections
    struct_wall_layers = selections.get("struct-cwall-layer") or []
    non_struct_wall_layers = selections.get("non-wall-layer") or []

    struct_layers_upper = {str(v).upper() for v in struct_wall_layers if v}
    non_struct_layers_upper = {str(v).upper() for v in non_struct_wall_layers if v}

    if not struct_layers_upper and not non_struct_layers_upper:
        return []

    # Get bbox from first border if available
    bbox = None
    if borders:
        bbox = borders[0].get("properties", {}).get("bbox_world")

    # Collect line segments by wall type
    struct_segments: list[tuple[tuple[float, float], tuple[float, float], str]] = []
    non_struct_segments: list[tuple[tuple[float, float], tuple[float, float], str]] = []

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") not in ("LINE", "LWPOLYLINE"):
            continue

        layer = str(ent.get("layer") or ent.get("layerName") or "").upper()

        # Filter by bbox if available
        if bbox:
            points = extract_points(ent)
            if points and not points_inside_bbox(points, bbox):
                continue

        segments = _extract_line_data(ent)

        if layer in struct_layers_upper:
            struct_segments.extend(segments)
        elif layer in non_struct_layers_upper:
            non_struct_segments.extend(segments)

    walls: list[dict[str, Any]] = []

    def find_walls(
        segments: list[tuple[tuple[float, float], tuple[float, float], str]],
        wall_type: str,
    ) -> None:
        """Find parallel line pairs and create wall records."""
        n = len(segments)
        used = [False] * n

        for i in range(n):
            if used[i]:
                continue

            start1, end1, handle1 = segments[i]
            dir1 = _line_direction(start1, end1)
            if dir1 == (0.0, 0.0):
                continue

            for j in range(i + 1, n):
                if used[j]:
                    continue

                start2, end2, handle2 = segments[j]
                dir2 = _line_direction(start2, end2)
                if dir2 == (0.0, 0.0):
                    continue

                # Check if parallel
                if not _are_parallel(dir1, dir2):
                    continue

                # Check perpendicular distance
                dist = _perpendicular_distance(start1, end1, start2, end2)
                if dist > max_thickness or dist < 1.0:  # Ignore coincident lines
                    continue

                # Check overlap
                if not _lines_overlap(start1, end1, start2, end2):
                    continue

                # Compute wall geometry
                geom = _compute_wall_geometry(start1, end1, start2, end2)
                if not geom or geom.get("length", 0) < min_length:
                    continue

                walls.append({
                    "file_id": file_id,
                    "wall_type": wall_type,
                    "handles": [handle1, handle2],
                    **geom,
                })

                used[i] = True
                used[j] = True
                break

    # Find structural walls
    find_walls(struct_segments, "structural")

    # Find non-structural walls
    find_walls(non_struct_segments, "non_structural")

    # Convert to semantic records
    records = []
    for idx, wall in enumerate(walls, start=1):
        wall_type = wall.pop("wall_type")
        kind = "structural_wall" if wall_type == "structural" else "partition_wall"

        records.append({
            "file_id": file_id,
            "kind": kind,
            "confidence": None,
            "source_rule": f"layer:{'struct-cwall-layer' if wall_type == 'structural' else 'non-wall-layer'}",
            "properties": {
                "wall_index": idx,
                **wall,
            },
        })

    return records
