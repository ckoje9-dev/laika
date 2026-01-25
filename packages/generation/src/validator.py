"""도면 스키마 검증."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from .schema import DrawingSchema

logger = logging.getLogger(__name__)


class ValidationResult:
    """검증 결과."""

    def __init__(self, valid: bool, errors: list[str] = None, warnings: list[str] = None):
        self.valid = valid
        self.errors = errors or []
        self.warnings = warnings or []

    def __bool__(self) -> bool:
        return self.valid

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class SchemaValidator:
    """JSON 스키마 구조 검증."""

    @staticmethod
    def validate(data: dict | str) -> ValidationResult:
        """Pydantic 스키마 검증."""
        errors = []

        # JSON 문자열이면 파싱
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                return ValidationResult(False, [f"JSON 파싱 오류: {e}"])

        # Pydantic 검증
        try:
            DrawingSchema.model_validate(data)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return ValidationResult(False, errors)

        return ValidationResult(True)

    @staticmethod
    def parse(data: dict | str) -> Optional[DrawingSchema]:
        """JSON을 DrawingSchema로 파싱."""
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return None

        try:
            return DrawingSchema.model_validate(data)
        except ValidationError:
            return None


class GeometryValidator:
    """기하학적 검증."""

    # 검증 한계값
    MAX_COORDINATE = 1_000_000  # 1km
    MIN_COLUMN_SIZE = 100  # 100mm
    MAX_COLUMN_SIZE = 2000  # 2m
    MIN_WALL_THICKNESS = 50  # 50mm
    MAX_WALL_THICKNESS = 1000  # 1m
    MIN_AXIS_SPACING = 1000  # 1m
    MAX_AXIS_SPACING = 20000  # 20m

    @classmethod
    def validate(cls, schema: DrawingSchema) -> ValidationResult:
        """기하학적 유효성 검증."""
        errors = []
        warnings = []

        # 축선 검증
        if schema.grid:
            cls._validate_grid(schema.grid, errors, warnings)

        # 기둥 검증
        for i, col in enumerate(schema.columns):
            cls._validate_column(col, i, errors, warnings)

        # 벽체 검증
        for i, wall in enumerate(schema.walls):
            cls._validate_wall(wall, i, errors, warnings)

        # 기둥-축선 정합성 검증
        if schema.grid and schema.columns:
            cls._validate_columns_on_grid(schema, warnings)

        return ValidationResult(len(errors) == 0, errors, warnings)

    @classmethod
    def _validate_grid(cls, grid, errors: list, warnings: list) -> None:
        """축선 검증."""
        # X축선 간격 검증
        x_positions = sorted(ax.position for ax in grid.x_axes)
        for i in range(1, len(x_positions)):
            spacing = x_positions[i] - x_positions[i - 1]
            if spacing < cls.MIN_AXIS_SPACING:
                warnings.append(f"X축선 간격이 너무 좁음: {spacing}mm (권장: {cls.MIN_AXIS_SPACING}mm 이상)")
            if spacing > cls.MAX_AXIS_SPACING:
                warnings.append(f"X축선 간격이 너무 넓음: {spacing}mm (권장: {cls.MAX_AXIS_SPACING}mm 이하)")

        # Y축선 간격 검증
        y_positions = sorted(ax.position for ax in grid.y_axes)
        for i in range(1, len(y_positions)):
            spacing = y_positions[i] - y_positions[i - 1]
            if spacing < cls.MIN_AXIS_SPACING:
                warnings.append(f"Y축선 간격이 너무 좁음: {spacing}mm (권장: {cls.MIN_AXIS_SPACING}mm 이상)")
            if spacing > cls.MAX_AXIS_SPACING:
                warnings.append(f"Y축선 간격이 너무 넓음: {spacing}mm (권장: {cls.MAX_AXIS_SPACING}mm 이하)")

    @classmethod
    def _validate_column(cls, col, index: int, errors: list, warnings: list) -> None:
        """기둥 검증."""
        # 좌표 범위
        if abs(col.position.x) > cls.MAX_COORDINATE or abs(col.position.y) > cls.MAX_COORDINATE:
            errors.append(f"기둥 {index}: 좌표가 범위를 벗어남")

        # 크기 검증
        if col.size.width < cls.MIN_COLUMN_SIZE or col.size.height < cls.MIN_COLUMN_SIZE:
            warnings.append(f"기둥 {index}: 크기가 너무 작음 ({col.size.width}x{col.size.height}mm)")
        if col.size.width > cls.MAX_COLUMN_SIZE or col.size.height > cls.MAX_COLUMN_SIZE:
            warnings.append(f"기둥 {index}: 크기가 너무 큼 ({col.size.width}x{col.size.height}mm)")

    @classmethod
    def _validate_wall(cls, wall, index: int, errors: list, warnings: list) -> None:
        """벽체 검증."""
        # 두께 검증
        if wall.thickness < cls.MIN_WALL_THICKNESS:
            warnings.append(f"벽체 {index}: 두께가 너무 얇음 ({wall.thickness}mm)")
        if wall.thickness > cls.MAX_WALL_THICKNESS:
            warnings.append(f"벽체 {index}: 두께가 너무 두꺼움 ({wall.thickness}mm)")

        # 길이 검증 (시작점 = 끝점이면 오류)
        if wall.start.x == wall.end.x and wall.start.y == wall.end.y:
            errors.append(f"벽체 {index}: 시작점과 끝점이 동일함")

    @classmethod
    def _validate_columns_on_grid(cls, schema: DrawingSchema, warnings: list) -> None:
        """기둥이 축선 교차점에 있는지 검증."""
        if not schema.grid:
            return

        x_positions = set(ax.position for ax in schema.grid.x_axes)
        y_positions = set(ax.position for ax in schema.grid.y_axes)
        tolerance = 100  # 100mm 허용 오차

        for i, col in enumerate(schema.columns):
            on_x = any(abs(col.position.x - xp) <= tolerance for xp in x_positions)
            on_y = any(abs(col.position.y - yp) <= tolerance for yp in y_positions)
            if not (on_x and on_y):
                warnings.append(f"기둥 {i}: 축선 교차점에서 벗어남 ({col.position.x}, {col.position.y})")


def validate_full(data: dict | str) -> ValidationResult:
    """전체 검증 (스키마 + 기하)."""
    # 1. 스키마 검증
    schema_result = SchemaValidator.validate(data)
    if not schema_result:
        return schema_result

    # 2. 파싱
    schema = SchemaValidator.parse(data)
    if not schema:
        return ValidationResult(False, ["스키마 파싱 실패"])

    # 3. 기하 검증
    geo_result = GeometryValidator.validate(schema)

    # 결과 합침
    all_errors = schema_result.errors + geo_result.errors
    all_warnings = schema_result.warnings + geo_result.warnings

    return ValidationResult(len(all_errors) == 0, all_errors, all_warnings)
