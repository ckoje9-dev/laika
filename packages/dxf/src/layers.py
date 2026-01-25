"""레이어 관리 모듈."""
from typing import Any

import ezdxf
from ezdxf.document import Drawing


# 기본 레이어 정의 (name, color, linetype)
DEFAULT_LAYERS: list[dict[str, Any]] = [
    {"name": "0", "color": 7, "linetype": "Continuous"},
    {"name": "BORDER", "color": 7, "linetype": "Continuous"},
    {"name": "AXIS", "color": 1, "linetype": "CENTER"},
    {"name": "COLUMN", "color": 3, "linetype": "Continuous"},
    {"name": "WALL", "color": 4, "linetype": "Continuous"},
    {"name": "DOOR", "color": 5, "linetype": "Continuous"},
    {"name": "WINDOW", "color": 6, "linetype": "Continuous"},
    {"name": "DIMENSION", "color": 2, "linetype": "Continuous"},
    {"name": "TEXT", "color": 7, "linetype": "Continuous"},
    {"name": "HATCH", "color": 8, "linetype": "Continuous"},
]


class LayerManager:
    """DXF 레이어 관리 클래스."""

    def __init__(self, doc: Drawing) -> None:
        self.doc = doc
        self._setup_linetypes()

    def _setup_linetypes(self) -> None:
        """기본 라인타입 설정."""
        linetypes = self.doc.linetypes
        if "CENTER" not in linetypes:
            linetypes.add("CENTER", pattern=[0.5, 0.25, -0.125, 0.0, -0.125])
        if "DASHED" not in linetypes:
            linetypes.add("DASHED", pattern=[0.5, 0.25, -0.25])
        if "HIDDEN" not in linetypes:
            linetypes.add("HIDDEN", pattern=[0.25, 0.125, -0.125])

    def add_layer(
        self,
        name: str,
        color: int = 7,
        linetype: str = "Continuous",
        lineweight: int = -1,
    ) -> None:
        """레이어 추가."""
        layers = self.doc.layers
        if name not in layers:
            layers.add(
                name,
                color=color,
                linetype=linetype,
                lineweight=lineweight,
            )

    def setup_default_layers(self) -> None:
        """기본 레이어 셋업."""
        for layer_def in DEFAULT_LAYERS:
            self.add_layer(
                name=layer_def["name"],
                color=layer_def.get("color", 7),
                linetype=layer_def.get("linetype", "Continuous"),
            )

    def set_layer_color(self, name: str, color: int) -> None:
        """레이어 색상 변경."""
        if name in self.doc.layers:
            self.doc.layers.get(name).color = color

    def get_layer_names(self) -> list[str]:
        """모든 레이어 이름 반환."""
        return [layer.dxf.name for layer in self.doc.layers]
