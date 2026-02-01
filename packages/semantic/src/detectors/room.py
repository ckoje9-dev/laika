"""Room detection from enclosed wall regions."""
from collections import defaultdict
from typing import Any

from ..geometry import polygon_area, point_in_polygon, polygon_centroid, distance, vertices_to_wkt_polygon


def _round_point(p: tuple[float, float], precision: float = 1.0) -> tuple[float, float]:
    """Round point coordinates for comparison."""
    return (round(p[0] / precision) * precision, round(p[1] / precision) * precision)


def _build_wall_graph(
    walls: list[dict[str, Any]],
    tolerance: float = 50.0,
) -> dict[tuple[float, float], list[tuple[tuple[float, float], int]]]:
    """Build adjacency graph from wall centerlines.

    Args:
        walls: List of wall records with start/end properties
        tolerance: Distance tolerance for connecting endpoints

    Returns:
        Adjacency list: node -> [(neighbor_node, wall_index), ...]
    """
    # Collect all endpoints
    endpoints: list[tuple[tuple[float, float], int, str]] = []  # (point, wall_idx, 'start'|'end')

    for idx, wall in enumerate(walls):
        props = wall.get("properties", {})
        start = props.get("start")
        end = props.get("end")

        if not start or not end:
            continue

        start_pt = (float(start.get("x", 0)), float(start.get("y", 0)))
        end_pt = (float(end.get("x", 0)), float(end.get("y", 0)))

        endpoints.append((start_pt, idx, "start"))
        endpoints.append((end_pt, idx, "end"))

    # Merge nearby points
    merged: dict[int, tuple[float, float]] = {}  # endpoint_idx -> merged_point
    used = [False] * len(endpoints)

    for i in range(len(endpoints)):
        if used[i]:
            continue

        cluster = [i]
        used[i] = True

        for j in range(i + 1, len(endpoints)):
            if used[j]:
                continue
            if distance(endpoints[i][0], endpoints[j][0]) <= tolerance:
                cluster.append(j)
                used[j] = True

        # Compute average point for cluster
        avg_x = sum(endpoints[k][0][0] for k in cluster) / len(cluster)
        avg_y = sum(endpoints[k][0][1] for k in cluster) / len(cluster)
        merged_pt = _round_point((avg_x, avg_y), 1.0)

        for k in cluster:
            merged[k] = merged_pt

    # Build adjacency graph
    graph: dict[tuple[float, float], list[tuple[tuple[float, float], int]]] = defaultdict(list)

    for idx, wall in enumerate(walls):
        props = wall.get("properties", {})
        start = props.get("start")
        end = props.get("end")

        if not start or not end:
            continue

        # Find merged points for this wall's endpoints
        start_merged = None
        end_merged = None

        for ep_idx, (pt, wall_idx, side) in enumerate(endpoints):
            if wall_idx == idx:
                if side == "start":
                    start_merged = merged.get(ep_idx)
                else:
                    end_merged = merged.get(ep_idx)

        if start_merged and end_merged and start_merged != end_merged:
            graph[start_merged].append((end_merged, idx))
            graph[end_merged].append((start_merged, idx))

    return dict(graph)


def _find_minimal_cycles(
    graph: dict[tuple[float, float], list[tuple[tuple[float, float], int]]],
    max_cycle_length: int = 20,
) -> list[list[tuple[float, float]]]:
    """Find all minimal cycles in the wall graph.

    Uses a modified DFS to find simple cycles.

    Args:
        graph: Adjacency list from _build_wall_graph
        max_cycle_length: Maximum number of vertices in a cycle

    Returns:
        List of cycles, each cycle is a list of vertices
    """
    if not graph:
        return []

    nodes = list(graph.keys())
    found_cycles: list[tuple[tuple[float, float], ...]] = []
    visited_edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()

    def dfs(
        start: tuple[float, float],
        current: tuple[float, float],
        path: list[tuple[float, float]],
        path_edges: set[tuple[tuple[float, float], tuple[float, float]]],
    ) -> None:
        if len(path) > max_cycle_length:
            return

        for neighbor, wall_idx in graph.get(current, []):
            edge = tuple(sorted([current, neighbor]))
            if edge in path_edges:
                continue

            if neighbor == start and len(path) >= 3:
                # Found a cycle
                cycle = tuple(path)
                # Normalize cycle (start from smallest vertex)
                min_idx = cycle.index(min(cycle))
                normalized = cycle[min_idx:] + cycle[:min_idx]
                # Check both directions
                reversed_cycle = tuple(reversed(normalized))
                if normalized not in found_cycles and reversed_cycle not in found_cycles:
                    found_cycles.append(normalized)
                continue

            if neighbor in path:
                continue

            new_path = path + [neighbor]
            new_edges = path_edges | {edge}
            dfs(start, neighbor, new_path, new_edges)

    # Start DFS from each node
    for start_node in nodes:
        dfs(start_node, start_node, [start_node], set())

    return [list(cycle) for cycle in found_cycles]


def _filter_minimal_cycles(cycles: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Filter out cycles that contain other cycles (keep only minimal/innermost).

    Args:
        cycles: List of cycles

    Returns:
        Filtered list of minimal cycles
    """
    if not cycles:
        return []

    # Sort by area (smallest first - these are likely minimal cycles)
    cycles_with_area = [(cycle, polygon_area(cycle)) for cycle in cycles]
    cycles_with_area.sort(key=lambda x: x[1])

    minimal: list[list[tuple[float, float]]] = []

    for cycle, area in cycles_with_area:
        if area < 100:  # Skip degenerate cycles
            continue

        centroid = polygon_centroid(cycle)
        if not centroid:
            continue

        # Check if this cycle's centroid is inside any already-found minimal cycle
        is_nested = False
        for existing in minimal:
            if point_in_polygon(centroid, existing):
                is_nested = True
                break

        if not is_nested:
            minimal.append(cycle)

    return minimal


def _extract_text_content(entity: dict[str, Any]) -> str | None:
    """Extract text content from TEXT or MTEXT entity."""
    dtype = entity.get("type")
    if dtype not in ("TEXT", "MTEXT"):
        return None

    # Try various text content fields
    text = entity.get("text") or entity.get("textString") or entity.get("contents")
    if isinstance(text, str) and text.strip():
        return text.strip()

    return None


def _get_text_position(entity: dict[str, Any]) -> tuple[float, float] | None:
    """Extract position from TEXT or MTEXT entity."""
    pos = entity.get("position") or entity.get("insertionPoint") or entity.get("startPoint")
    if isinstance(pos, dict):
        x = pos.get("x")
        y = pos.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return (float(x), float(y))
    return None


def build_room_records(
    file_id: str,
    walls: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    endpoint_tolerance: float = 50.0,
) -> list[dict[str, Any]]:
    """Detect rooms as enclosed regions formed by wall centerlines.

    Args:
        file_id: File UUID
        walls: List of wall semantic records
        entities: List of DXF entities (for TEXT extraction)
        endpoint_tolerance: Distance tolerance for connecting wall endpoints

    Returns:
        List of room semantic records
    """
    if not walls:
        return []

    # Build wall graph
    graph = _build_wall_graph(walls, tolerance=endpoint_tolerance)
    if not graph:
        return []

    # Find cycles
    cycles = _find_minimal_cycles(graph)
    if not cycles:
        return []

    # Filter to minimal cycles
    minimal_cycles = _filter_minimal_cycles(cycles)
    if not minimal_cycles:
        return []

    # Collect TEXT entities
    text_entities: list[tuple[tuple[float, float], str]] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        text = _extract_text_content(ent)
        pos = _get_text_position(ent)
        if text and pos:
            text_entities.append((pos, text))

    # Create room records
    records: list[dict[str, Any]] = []

    for idx, cycle in enumerate(minimal_cycles, start=1):
        area = polygon_area(cycle)
        centroid = polygon_centroid(cycle)

        # Find TEXT inside this room
        room_texts: list[str] = []
        for pos, text in text_entities:
            if point_in_polygon(pos, cycle):
                room_texts.append(text)

        # Determine room name from texts
        room_name = None
        if room_texts:
            # Use the first non-numeric text as room name
            for txt in room_texts:
                # Skip pure numbers or dimension-like texts
                if not txt.replace(".", "").replace(",", "").replace("-", "").isdigit():
                    room_name = txt
                    break
            if not room_name:
                room_name = room_texts[0]

        # Compute bounding box
        xs = [p[0] for p in cycle]
        ys = [p[1] for p in cycle]

        # Generate WKT for PostGIS
        geom_wkt = vertices_to_wkt_polygon(cycle)

        records.append({
            "file_id": file_id,
            "kind": "room",
            "confidence": None,
            "source_rule": "wall_enclosure",
            "geom_wkt": geom_wkt,  # For PostGIS storage
            "properties": {
                "room_index": idx,
                "name": room_name,
                "area": round(area, 2),
                "area_sqm": round(area / 1_000_000, 2),  # mm² to m²
                "centroid": {"x": round(centroid[0], 2), "y": round(centroid[1], 2)} if centroid else None,
                "bbox": {
                    "xmin": round(min(xs), 2),
                    "ymin": round(min(ys), 2),
                    "xmax": round(max(xs), 2),
                    "ymax": round(max(ys), 2),
                },
                "vertices": [{"x": round(p[0], 2), "y": round(p[1], 2)} for p in cycle],
                "vertex_count": len(cycle),
                "texts_inside": room_texts,
            },
        })

    return records
