"""Door detection and room connectivity analysis."""
from typing import Any

from ..geometry import distance, point_in_polygon, extract_points, point_to_wkt


def _get_entity_center(entity: dict[str, Any]) -> tuple[float, float] | None:
    """Extract center point from various entity types."""
    dtype = entity.get("type")

    # ARC - common for door swing representation
    if dtype == "ARC":
        center = entity.get("center")
        if isinstance(center, dict):
            x = center.get("x")
            y = center.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return (float(x), float(y))

    # CIRCLE
    if dtype == "CIRCLE":
        center = entity.get("center") or entity.get("position")
        if isinstance(center, dict):
            x = center.get("x")
            y = center.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return (float(x), float(y))

    # INSERT (block reference) - door blocks
    if dtype == "INSERT":
        pos = entity.get("position")
        if isinstance(pos, dict):
            x = pos.get("x")
            y = pos.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return (float(x), float(y))

    # LINE or LWPOLYLINE - compute center from points
    if dtype in ("LINE", "LWPOLYLINE"):
        points = extract_points(entity)
        if points:
            avg_x = sum(p[0] for p in points) / len(points)
            avg_y = sum(p[1] for p in points) / len(points)
            return (avg_x, avg_y)

    return None


def _get_entity_width(entity: dict[str, Any]) -> float:
    """Estimate door width from entity."""
    dtype = entity.get("type")

    # ARC - radius is typically door width
    if dtype == "ARC":
        radius = entity.get("radius")
        if isinstance(radius, (int, float)):
            return float(radius)

    # LINE - length is door width
    if dtype == "LINE":
        points = extract_points(entity)
        if len(points) >= 2:
            return distance(points[0], points[1])

    # LWPOLYLINE - bounding box
    if dtype == "LWPOLYLINE":
        points = extract_points(entity)
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            return max(width, height)

    # Default door width
    return 900.0


def _find_nearest_wall(
    door_center: tuple[float, float],
    walls: list[dict[str, Any]],
    max_distance: float = 500.0,
) -> dict[str, Any] | None:
    """Find the wall closest to door center."""
    best_wall = None
    best_dist = float('inf')

    for wall in walls:
        props = wall.get("properties", {})
        start = props.get("start")
        end = props.get("end")

        if not start or not end:
            continue

        # Calculate distance from door center to wall centerline
        wall_start = (float(start.get("x", 0)), float(start.get("y", 0)))
        wall_end = (float(end.get("x", 0)), float(end.get("y", 0)))

        # Point-to-line-segment distance
        dist = _point_to_segment_distance(door_center, wall_start, wall_end)

        if dist < best_dist and dist <= max_distance:
            best_dist = dist
            best_wall = wall

    return best_wall


def _point_to_segment_distance(
    point: tuple[float, float],
    seg_start: tuple[float, float],
    seg_end: tuple[float, float],
) -> float:
    """Calculate minimum distance from point to line segment."""
    px, py = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-9:
        return distance(point, seg_start)

    # Parameter t for closest point on line
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))

    # Closest point on segment
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return distance(point, (closest_x, closest_y))


def _find_adjacent_rooms(
    door_center: tuple[float, float],
    wall: dict[str, Any],
    rooms: list[dict[str, Any]],
    search_offset: float = 300.0,
) -> list[dict[str, Any]]:
    """Find rooms on both sides of the door/wall.

    Creates test points perpendicular to wall direction and checks
    which rooms contain those points.
    """
    props = wall.get("properties", {})
    direction = props.get("direction", {})
    thickness = props.get("thickness", 200)

    dx = float(direction.get("x", 1))
    dy = float(direction.get("y", 0))

    # Normal vector (perpendicular to wall)
    nx, ny = -dy, dx

    # Test points on both sides of wall
    offset = (thickness / 2) + search_offset
    test_point1 = (door_center[0] + nx * offset, door_center[1] + ny * offset)
    test_point2 = (door_center[0] - nx * offset, door_center[1] - ny * offset)

    adjacent_rooms: list[dict[str, Any]] = []

    for room in rooms:
        vertices = room.get("properties", {}).get("vertices", [])
        if not vertices:
            continue

        polygon = [(v.get("x", 0), v.get("y", 0)) for v in vertices]

        if point_in_polygon(test_point1, polygon) or point_in_polygon(test_point2, polygon):
            adjacent_rooms.append(room)

    return adjacent_rooms


def _is_door_on_wall(
    door_center: tuple[float, float],
    door_width: float,
    wall: dict[str, Any],
    tolerance: float = 100.0,
) -> bool:
    """Check if door is positioned on the wall."""
    props = wall.get("properties", {})
    start = props.get("start")
    end = props.get("end")
    thickness = props.get("thickness", 200)

    if not start or not end:
        return False

    wall_start = (float(start.get("x", 0)), float(start.get("y", 0)))
    wall_end = (float(end.get("x", 0)), float(end.get("y", 0)))

    # Distance from door center to wall centerline
    dist = _point_to_segment_distance(door_center, wall_start, wall_end)

    # Door should be within wall thickness + tolerance
    return dist <= (thickness / 2) + tolerance


def build_door_records(
    file_id: str,
    walls: list[dict[str, Any]],
    rooms: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    selections: dict[str, list[str]] | None,
    max_wall_distance: float = 500.0,
) -> list[dict[str, Any]]:
    """Detect doors and their room connectivity.

    Args:
        file_id: File UUID
        walls: List of wall semantic records
        rooms: List of room semantic records
        entities: List of DXF entities
        selections: User selections with door layer mappings
        max_wall_distance: Maximum distance from door to wall

    Returns:
        List of door semantic records with room connectivity
    """
    if not selections:
        return []

    # Get door layers from selections
    door_layers = selections.get("non-door-layer") or []
    door_layers_upper = {str(v).upper() for v in door_layers if v}

    if not door_layers_upper:
        return []

    # Collect door entities
    door_entities: list[dict[str, Any]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue

        layer = str(ent.get("layer") or ent.get("layerName") or "").upper()
        if layer not in door_layers_upper:
            continue

        center = _get_entity_center(ent)
        if center:
            door_entities.append({
                "entity": ent,
                "center": center,
                "width": _get_entity_width(ent),
            })

    if not door_entities:
        return []

    records: list[dict[str, Any]] = []
    room_connections: dict[int, set[int]] = {}  # room_index -> connected room indices

    for idx, door_data in enumerate(door_entities, start=1):
        center = door_data["center"]
        width = door_data["width"]
        entity = door_data["entity"]

        # Find nearest wall
        wall = _find_nearest_wall(center, walls, max_wall_distance)

        wall_info = None
        if wall:
            wall_props = wall.get("properties", {})
            wall_info = {
                "wall_index": wall_props.get("wall_index"),
                "wall_type": wall.get("kind"),
            }

            # Find adjacent rooms
            adjacent_rooms = _find_adjacent_rooms(center, wall, rooms)

            # Build room connectivity
            room_indices = []
            room_names = []
            for room in adjacent_rooms:
                room_props = room.get("properties", {})
                room_idx = room_props.get("room_index")
                room_name = room_props.get("name")
                if room_idx:
                    room_indices.append(room_idx)
                    room_names.append(room_name)

            # Update connectivity graph
            if len(room_indices) >= 2:
                for i, ri in enumerate(room_indices):
                    if ri not in room_connections:
                        room_connections[ri] = set()
                    for j, rj in enumerate(room_indices):
                        if i != j:
                            room_connections[ri].add(rj)
        else:
            room_indices = []
            room_names = []

        # Generate WKT for PostGIS
        geom_wkt = point_to_wkt(center)

        records.append({
            "file_id": file_id,
            "kind": "door",
            "confidence": None,
            "source_rule": "layer:non-door-layer",
            "geom_wkt": geom_wkt,  # For PostGIS storage
            "properties": {
                "door_index": idx,
                "center": {"x": round(center[0], 2), "y": round(center[1], 2)},
                "width": round(width, 2),
                "entity_type": entity.get("type"),
                "entity_handle": entity.get("handle"),
                "wall": wall_info,
                "connects_rooms": room_indices,
                "connects_room_names": room_names,
            },
        })

    # Add room connectivity summary record
    if room_connections:
        connectivity_edges = []
        seen = set()
        for room_a, connected in room_connections.items():
            for room_b in connected:
                edge = tuple(sorted([room_a, room_b]))
                if edge not in seen:
                    seen.add(edge)
                    connectivity_edges.append({"from": edge[0], "to": edge[1]})

        records.append({
            "file_id": file_id,
            "kind": "room_connectivity",
            "confidence": None,
            "source_rule": "door_analysis",
            "properties": {
                "edges": connectivity_edges,
                "room_count": len(room_connections),
                "door_count": len(door_entities),
            },
        })

    return records
