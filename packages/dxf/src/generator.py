"""DXF 생성기 메인 클래스."""
import logging
from pathlib import Path
from typing import Any, Optional

import ezdxf
from ezdxf.document import Drawing

from .layers import LayerManager
from .entities import (
    create_line,
    create_polyline,
    create_circle,
    create_text,
    create_rectangle,
)

logger = logging.getLogger(__name__)


class DxfGenerator:
    """DXF 파일 생성기."""

    def __init__(self, dxfversion: str = "R2013") -> None:
        """
        DXF 생성기 초기화.

        Args:
            dxfversion: DXF 버전 (R12, R2000, R2004, R2007, R2010, R2013, R2018)
        """
        self.doc: Drawing = ezdxf.new(dxfversion)
        self.msp = self.doc.modelspace()
        self.layer_manager = LayerManager(self.doc)
        self.layer_manager.setup_default_layers()

    def add_grid(
        self,
        x_positions: list[float],
        y_positions: list[float],
        x_labels: Optional[list[str]] = None,
        y_labels: Optional[list[str]] = None,
        extend: float = 500.0,
    ) -> None:
        """그리드(축선) 추가."""
        x_labels = x_labels or [f"X{i+1}" for i in range(len(x_positions))]
        y_labels = y_labels or [f"Y{i+1}" for i in range(len(y_positions))]

        y_min = min(y_positions) - extend
        y_max = max(y_positions) + extend
        x_min = min(x_positions) - extend
        x_max = max(x_positions) + extend

        # X축선 (수직선)
        for x, label in zip(x_positions, x_labels):
            create_line(self.msp, (x, y_min), (x, y_max), layer="AXIS")
            create_text(self.msp, label, (x, y_max + 100), height=150, layer="AXIS")

        # Y축선 (수평선)
        for y, label in zip(y_positions, y_labels):
            create_line(self.msp, (x_min, y), (x_max, y), layer="AXIS")
            create_text(self.msp, label, (x_min - 200, y), height=150, layer="AXIS")

    def add_columns(
        self,
        positions: list[tuple[float, float]],
        size: tuple[float, float] = (600, 600),
    ) -> None:
        """기둥 추가."""
        w, h = size
        for x, y in positions:
            create_rectangle(
                self.msp,
                (x - w / 2, y - h / 2),
                (x + w / 2, y + h / 2),
                layer="COLUMN",
            )

    def add_walls(
        self,
        segments: list[tuple[tuple[float, float], tuple[float, float], float]],
    ) -> None:
        """
        벽체 추가.

        Args:
            segments: [(시작점, 끝점, 두께), ...]
        """
        for start, end, thickness in segments:
            # 벽 중심선을 기준으로 두께만큼 오프셋
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = (dx**2 + dy**2) ** 0.5
            if length == 0:
                continue

            # 법선 벡터
            nx, ny = -dy / length * thickness / 2, dx / length * thickness / 2

            points = [
                (start[0] + nx, start[1] + ny),
                (end[0] + nx, end[1] + ny),
                (end[0] - nx, end[1] - ny),
                (start[0] - nx, start[1] - ny),
            ]
            create_polyline(self.msp, points, layer="WALL", closed=True)

    def add_border(
        self,
        width: float,
        height: float,
        margin: float = 10.0,
        title_block: bool = True,
    ) -> None:
        """도곽 추가."""
        # 외곽선
        create_rectangle(
            self.msp,
            (margin, margin),
            (width - margin, height - margin),
            layer="BORDER",
        )

        if title_block:
            # 타이틀 블록 (우측 하단)
            tb_width = 180
            tb_height = 60
            tb_x = width - margin - tb_width
            tb_y = margin
            create_rectangle(
                self.msp,
                (tb_x, tb_y),
                (tb_x + tb_width, tb_y + tb_height),
                layer="BORDER",
            )

    def add_opening(
        self,
        position: tuple[float, float],
        width: float,
        opening_type: str = "door",
        wall_thickness: float = 200,
    ) -> None:
        """개구부(문/창문) 추가."""
        x, y = position
        layer = "DOOR" if opening_type == "door" else "WINDOW"

        if opening_type == "door":
            # 문: 호(arc)로 표현
            create_line(self.msp, (x, y), (x + width, y), layer=layer)
            # 간단한 스윙 표시
            arc_points = [
                (x, y),
                (x + width * 0.7, y + width * 0.7),
                (x + width, y),
            ]
            create_polyline(self.msp, arc_points, layer=layer)
        else:
            # 창문: 이중선
            create_line(self.msp, (x, y - wall_thickness / 4), (x + width, y - wall_thickness / 4), layer=layer)
            create_line(self.msp, (x, y + wall_thickness / 4), (x + width, y + wall_thickness / 4), layer=layer)

    def from_semantic_objects(self, objects: list[dict[str, Any]]) -> None:
        """시맨틱 객체로부터 DXF 생성."""
        for obj in objects:
            kind = obj.get("kind")
            props = obj.get("properties", {})

            if kind == "axis_summary":
                x_axes = props.get("x_axes", [])
                y_axes = props.get("y_axes", [])
                x_positions = [ax.get("position", 0) for ax in x_axes]
                y_positions = [ax.get("position", 0) for ax in y_axes]
                x_labels = [ax.get("label", f"X{i}") for i, ax in enumerate(x_axes)]
                y_labels = [ax.get("label", f"Y{i}") for i, ax in enumerate(y_axes)]
                self.add_grid(x_positions, y_positions, x_labels, y_labels)

            elif kind == "concrete_column":
                center = props.get("center", {})
                size = props.get("size", {})
                if center:
                    pos = (center.get("x", 0), center.get("y", 0))
                    col_size = (size.get("width", 600), size.get("height", 600))
                    self.add_columns([pos], col_size)

            elif kind == "border":
                bbox = props.get("bbox_world", {})
                if bbox:
                    width = bbox.get("xmax", 0) - bbox.get("xmin", 0)
                    height = bbox.get("ymax", 0) - bbox.get("ymin", 0)
                    self.add_border(width, height)

    def save(self, path: str | Path) -> Path:
        """DXF 파일 저장."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.saveas(str(path))
        logger.info("DXF 저장 완료: %s", path)
        return path
