"""도면 생성을 위한 시맨틱 스키마 정의."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Point2D(BaseModel):
    """2D 좌표."""
    x: float
    y: float


class Size2D(BaseModel):
    """2D 크기."""
    width: float
    height: float


class AxisLine(BaseModel):
    """단일 축선."""
    label: str = Field(..., description="축선 라벨 (예: X1, Y2)")
    position: float = Field(..., description="축선 위치 (mm)")


class AxisGrid(BaseModel):
    """축선 그리드."""
    x_axes: list[AxisLine] = Field(default_factory=list, description="X방향 축선 (수직선)")
    y_axes: list[AxisLine] = Field(default_factory=list, description="Y방향 축선 (수평선)")

    @property
    def x_positions(self) -> list[float]:
        return [ax.position for ax in self.x_axes]

    @property
    def y_positions(self) -> list[float]:
        return [ax.position for ax in self.y_axes]

    @property
    def x_labels(self) -> list[str]:
        return [ax.label for ax in self.x_axes]

    @property
    def y_labels(self) -> list[str]:
        return [ax.label for ax in self.y_axes]


class Column(BaseModel):
    """기둥."""
    position: Point2D = Field(..., description="기둥 중심 좌표")
    size: Size2D = Field(default_factory=lambda: Size2D(width=600, height=600))
    shape: Literal["rect", "circle"] = "rect"
    material: Literal["concrete", "steel"] = "concrete"
    label: Optional[str] = None


class Wall(BaseModel):
    """벽체."""
    start: Point2D = Field(..., description="시작점")
    end: Point2D = Field(..., description="끝점")
    thickness: float = Field(default=200, description="벽 두께 (mm)")
    material: Literal["concrete", "masonry", "drywall"] = "concrete"


class Opening(BaseModel):
    """개구부 (문/창문)."""
    position: Point2D = Field(..., description="개구부 시작 위치")
    width: float = Field(..., description="개구부 폭")
    height: Optional[float] = Field(default=None, description="개구부 높이 (창문용)")
    type: Literal["door", "window"] = "door"
    wall_index: Optional[int] = Field(default=None, description="소속 벽체 인덱스")


class Border(BaseModel):
    """도곽."""
    width: float = Field(..., description="도곽 폭")
    height: float = Field(..., description="도곽 높이")
    margin: float = Field(default=10, description="여백")
    title_block: bool = Field(default=True, description="타이틀 블록 포함 여부")


class DrawingMetadata(BaseModel):
    """도면 메타데이터."""
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Literal["mm", "m", "cm"] = "mm"
    scale: str = "1:100"


class DrawingSchema(BaseModel):
    """전체 도면 스키마."""
    metadata: DrawingMetadata = Field(default_factory=DrawingMetadata)
    border: Optional[Border] = None
    grid: Optional[AxisGrid] = None
    columns: list[Column] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)

    def to_prompt_context(self) -> str:
        """LLM 컨텍스트용 텍스트 변환."""
        parts = []
        if self.grid:
            x_info = ", ".join(f"{ax.label}={ax.position}" for ax in self.grid.x_axes)
            y_info = ", ".join(f"{ax.label}={ax.position}" for ax in self.grid.y_axes)
            parts.append(f"축선: X방향[{x_info}], Y방향[{y_info}]")
        if self.columns:
            parts.append(f"기둥: {len(self.columns)}개")
        if self.walls:
            parts.append(f"벽체: {len(self.walls)}개")
        if self.openings:
            doors = sum(1 for o in self.openings if o.type == "door")
            windows = sum(1 for o in self.openings if o.type == "window")
            parts.append(f"개구부: 문 {doors}개, 창문 {windows}개")
        return "\n".join(parts) if parts else "빈 도면"

    @classmethod
    def example(cls) -> "DrawingSchema":
        """예시 스키마 생성."""
        return cls(
            metadata=DrawingMetadata(name="예시 도면", unit="mm", scale="1:100"),
            border=Border(width=841, height=594),
            grid=AxisGrid(
                x_axes=[
                    AxisLine(label="X1", position=0),
                    AxisLine(label="X2", position=7000),
                    AxisLine(label="X3", position=14000),
                ],
                y_axes=[
                    AxisLine(label="Y1", position=0),
                    AxisLine(label="Y2", position=7000),
                ],
            ),
            columns=[
                Column(position=Point2D(x=0, y=0), size=Size2D(width=600, height=600)),
                Column(position=Point2D(x=7000, y=0), size=Size2D(width=600, height=600)),
                Column(position=Point2D(x=14000, y=0), size=Size2D(width=600, height=600)),
                Column(position=Point2D(x=0, y=7000), size=Size2D(width=600, height=600)),
                Column(position=Point2D(x=7000, y=7000), size=Size2D(width=600, height=600)),
                Column(position=Point2D(x=14000, y=7000), size=Size2D(width=600, height=600)),
            ],
        )
