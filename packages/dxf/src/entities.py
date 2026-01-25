"""DXF 엔티티 생성 헬퍼 함수."""
from typing import Any, Sequence

from ezdxf.layouts import Modelspace


def create_line(
    msp: Modelspace,
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str = "0",
    color: int | None = None,
) -> Any:
    """LINE 엔티티 생성."""
    attribs = {"layer": layer}
    if color is not None:
        attribs["color"] = color
    return msp.add_line(start, end, dxfattribs=attribs)


def create_polyline(
    msp: Modelspace,
    points: Sequence[tuple[float, float]],
    layer: str = "0",
    closed: bool = False,
    color: int | None = None,
) -> Any:
    """LWPOLYLINE 엔티티 생성."""
    attribs = {"layer": layer}
    if color is not None:
        attribs["color"] = color
    return msp.add_lwpolyline(points, close=closed, dxfattribs=attribs)


def create_circle(
    msp: Modelspace,
    center: tuple[float, float],
    radius: float,
    layer: str = "0",
    color: int | None = None,
) -> Any:
    """CIRCLE 엔티티 생성."""
    attribs = {"layer": layer}
    if color is not None:
        attribs["color"] = color
    return msp.add_circle(center, radius, dxfattribs=attribs)


def create_text(
    msp: Modelspace,
    text: str,
    insert: tuple[float, float],
    height: float = 2.5,
    layer: str = "TEXT",
    rotation: float = 0.0,
    color: int | None = None,
) -> Any:
    """TEXT 엔티티 생성."""
    attribs = {"layer": layer, "rotation": rotation}
    if color is not None:
        attribs["color"] = color
    return msp.add_text(text, height=height, dxfattribs=attribs).set_placement(insert)


def create_dimension(
    msp: Modelspace,
    p1: tuple[float, float],
    p2: tuple[float, float],
    distance: float,
    layer: str = "DIMENSION",
    angle: float = 0.0,
) -> Any:
    """LINEAR DIMENSION 엔티티 생성."""
    # 수평/수직 치수선
    if abs(angle) < 1:  # 수평
        location = ((p1[0] + p2[0]) / 2, p1[1] + distance)
    else:  # 수직
        location = (p1[0] + distance, (p1[1] + p2[1]) / 2)

    return msp.add_linear_dim(
        base=location,
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle="Standard",
        dxfattribs={"layer": layer},
    ).render()


def create_block_ref(
    msp: Modelspace,
    block_name: str,
    insert: tuple[float, float],
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    rotation: float = 0.0,
    layer: str = "0",
) -> Any:
    """블록 참조(INSERT) 생성."""
    return msp.add_blockref(
        block_name,
        insert,
        dxfattribs={
            "layer": layer,
            "xscale": scale[0],
            "yscale": scale[1],
            "zscale": scale[2],
            "rotation": rotation,
        },
    )


def create_rectangle(
    msp: Modelspace,
    corner1: tuple[float, float],
    corner2: tuple[float, float],
    layer: str = "0",
    color: int | None = None,
) -> Any:
    """직사각형(닫힌 LWPOLYLINE) 생성."""
    x1, y1 = corner1
    x2, y2 = corner2
    points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return create_polyline(msp, points, layer=layer, closed=True, color=color)


def create_hatch(
    msp: Modelspace,
    points: Sequence[tuple[float, float]],
    pattern: str = "SOLID",
    layer: str = "HATCH",
    color: int | None = None,
) -> Any:
    """HATCH 엔티티 생성."""
    attribs = {"layer": layer}
    if color is not None:
        attribs["color"] = color
    hatch = msp.add_hatch(color=color or 256, dxfattribs=attribs)
    hatch.paths.add_polyline_path(points, is_closed=True)
    hatch.set_pattern_fill(pattern)
    return hatch
