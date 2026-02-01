"""Geometric utility functions."""
import math
from typing import Any, Optional


def extract_points(entity: dict[str, Any]) -> list[tuple[float, float]]:
    """Extract coordinate points from LINE or LWPOLYLINE entities.

    Args:
        entity: DXF entity dictionary

    Returns:
        List of (x, y) tuples
    """
    dtype = entity.get("type")

    if dtype == "LINE":
        # Try vertices array first
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

        # Fallback to startPoint/endPoint
        sp = entity.get("startPoint") or entity.get("start") or entity.get("start_point")
        ep = entity.get("endPoint") or entity.get("end") or entity.get("end_point")
        if isinstance(sp, dict) and isinstance(ep, dict):
            return [
                (float(sp.get("x", 0)), float(sp.get("y", 0))),
                (float(ep.get("x", 0)), float(ep.get("y", 0)))
            ]

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


def points_inside_bbox(points: list[tuple[float, float]], bbox: dict[str, float]) -> bool:
    """Check if all points are inside bounding box.

    Args:
        points: List of (x, y) tuples
        bbox: Dictionary with keys: xmin, ymin, xmax, ymax

    Returns:
        True if all points are inside bbox
    """
    for x, y in points:
        if x < bbox["xmin"] or x > bbox["xmax"] or y < bbox["ymin"] or y > bbox["ymax"]:
            return False
    return True


def axis_orientation(points: list[tuple[float, float]], eps: float = 1e-6) -> tuple[str, float] | None:
    """Determine if points form a horizontal (X_AXIS) or vertical (Y_AXIS) line.

    Args:
        points: List of (x, y) tuples
        eps: Tolerance for axis alignment

    Returns:
        Tuple of (axis_type, coordinate) or None
        - ("Y_AXIS", x_coord) for vertical line
        - ("X_AXIS", y_coord) for horizontal line
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    if not xs or not ys:
        return None

    # Vertical line (constant X)
    if max(xs) - min(xs) < eps:
        return "Y_AXIS", sum(xs) / len(xs)

    # Horizontal line (constant Y)
    if max(ys) - min(ys) < eps:
        return "X_AXIS", sum(ys) / len(ys)

    return None


def block_bbox_from_entities(block_entities: list[dict[str, Any]]) -> dict[str, float] | None:
    """Compute bounding box from block entities.

    Args:
        block_entities: List of entities in a block definition

    Returns:
        Dictionary with keys: min_x, min_y, max_x, max_y, or None
    """
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


def transform_bbox(bbox: dict[str, float], insert: dict[str, Any]) -> dict[str, float]:
    """Transform local bbox to world coordinates using INSERT transformation.

    Args:
        bbox: Local bounding box with keys: min_x, min_y, max_x, max_y
        insert: INSERT entity with position, scale, rotation

    Returns:
        World bounding box with keys: xmin, ymin, xmax, ymax
    """
    # Extract transformation parameters
    tx = (insert.get("position") or {}).get("x", 0) if isinstance(insert.get("position"), dict) else insert.get("x", 0)
    ty = (insert.get("position") or {}).get("y", 0) if isinstance(insert.get("position"), dict) else insert.get("y", 0)
    sx = insert.get("xScale") or 1
    sy = insert.get("yScale") or 1
    rot = insert.get("rotation") or 0

    theta = math.radians(rot)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Transform all four corners
    corners = [
        (bbox["min_x"], bbox["min_y"]),
        (bbox["max_x"], bbox["min_y"]),
        (bbox["max_x"], bbox["max_y"]),
        (bbox["min_x"], bbox["max_y"]),
    ]

    world_points: list[tuple[float, float]] = []
    for x, y in corners:
        # Scale
        xs = x * sx
        ys = y * sy
        # Rotate
        xr = xs * cos_t - ys * sin_t
        yr = xs * sin_t + ys * cos_t
        # Translate
        xw = xr + tx
        yw = yr + ty
        world_points.append((xw, yw))

    # Compute world bbox
    xs = [p[0] for p in world_points]
    ys = [p[1] for p in world_points]

    return {
        "xmin": min(xs),
        "ymin": min(ys),
        "xmax": max(xs),
        "ymax": max(ys)
    }


def axis_intersections(summary: dict[str, Any]) -> list[tuple[float, float]]:
    """Compute grid intersection points from axis summary.

    Args:
        summary: Axis summary with x_axes and y_axes

    Returns:
        List of (x, y) intersection coordinates
    """
    x_axes = summary.get("x_axes") or []
    y_axes = summary.get("y_axes") or []

    xs = [a.get("coord") for a in y_axes if isinstance(a, dict) and isinstance(a.get("coord"), (int, float))]
    ys = [a.get("coord") for a in x_axes if isinstance(a, dict) and isinstance(a.get("coord"), (int, float))]

    return [(float(x), float(y)) for x in xs for y in ys]


def entity_center_and_size(entity: dict[str, Any]) -> tuple[float, float, dict[str, Any]] | None:
    """Compute center point and size from CIRCLE or POLYLINE entities.

    Args:
        entity: DXF entity dictionary

    Returns:
        Tuple of (center_x, center_y, size_dict) or None
        size_dict contains: shape, radius/diameter for circles, width/height for rects
    """
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


def match_intersection(center: tuple[float, float], intersections: list[tuple[float, float]], eps: float) -> bool:
    """Check if center point matches any intersection point within tolerance.

    Args:
        center: (x, y) center point
        intersections: List of (x, y) intersection points
        eps: Distance tolerance

    Returns:
        True if center matches any intersection
    """
    cx, cy = center
    for ix, iy in intersections:
        if abs(cx - ix) <= eps and abs(cy - iy) <= eps:
            return True
    return False


def polygon_area(vertices: list[tuple[float, float]]) -> float:
    """Calculate polygon area using Shoelace formula.

    Args:
        vertices: List of (x, y) vertices in order (clockwise or counter-clockwise)

    Returns:
        Absolute area of the polygon
    """
    n = len(vertices)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]

    return abs(area) / 2.0


def point_in_polygon(point: tuple[float, float], vertices: list[tuple[float, float]]) -> bool:
    """Check if point is inside polygon using ray casting algorithm.

    Args:
        point: (x, y) point to test
        vertices: List of (x, y) polygon vertices

    Returns:
        True if point is inside polygon
    """
    n = len(vertices)
    if n < 3:
        return False

    x, y = point
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


def polygon_centroid(vertices: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Calculate polygon centroid (center of mass).

    Args:
        vertices: List of (x, y) vertices

    Returns:
        (x, y) centroid or None if invalid polygon
    """
    n = len(vertices)
    if n < 3:
        return None

    # Signed area
    signed_area = 0.0
    cx = 0.0
    cy = 0.0

    for i in range(n):
        j = (i + 1) % n
        cross = vertices[i][0] * vertices[j][1] - vertices[j][0] * vertices[i][1]
        signed_area += cross
        cx += (vertices[i][0] + vertices[j][0]) * cross
        cy += (vertices[i][1] + vertices[j][1]) * cross

    if abs(signed_area) < 1e-9:
        # Degenerate polygon, return simple average
        return (
            sum(v[0] for v in vertices) / n,
            sum(v[1] for v in vertices) / n,
        )

    signed_area /= 2.0
    cx /= (6.0 * signed_area)
    cy /= (6.0 * signed_area)

    return (cx, cy)


def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.sqrt(dx * dx + dy * dy)


def vertices_to_wkt_polygon(vertices: list[tuple[float, float]]) -> str | None:
    """Convert vertices to WKT POLYGON string for PostGIS.

    Args:
        vertices: List of (x, y) tuples forming a closed polygon

    Returns:
        WKT string like 'POLYGON((x1 y1, x2 y2, ..., x1 y1))'
    """
    if len(vertices) < 3:
        return None

    # Ensure polygon is closed
    if vertices[0] != vertices[-1]:
        vertices = list(vertices) + [vertices[0]]

    coords = ", ".join(f"{x} {y}" for x, y in vertices)
    return f"POLYGON(({coords}))"


def vertices_to_wkt_linestring(vertices: list[tuple[float, float]]) -> str | None:
    """Convert vertices to WKT LINESTRING string for PostGIS.

    Args:
        vertices: List of (x, y) tuples

    Returns:
        WKT string like 'LINESTRING(x1 y1, x2 y2, ...)'
    """
    if len(vertices) < 2:
        return None

    coords = ", ".join(f"{x} {y}" for x, y in vertices)
    return f"LINESTRING({coords})"


def point_to_wkt(point: tuple[float, float]) -> str:
    """Convert point to WKT POINT string for PostGIS.

    Args:
        point: (x, y) tuple

    Returns:
        WKT string like 'POINT(x y)'
    """
    return f"POINT({point[0]} {point[1]})"
