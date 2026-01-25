"""도면 생성기 - LLM + Validator + DXF 생성 통합."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from pathlib import Path

from .schema import DrawingSchema
from .prompts import GenerationPrompts
from .validator import SchemaValidator, GeometryValidator, validate_full, ValidationResult

logger = logging.getLogger(__name__)


class GenerationResult:
    """생성 결과."""

    def __init__(
        self,
        success: bool,
        schema: Optional[DrawingSchema] = None,
        dxf_path: Optional[Path] = None,
        raw_json: Optional[str] = None,
        validation: Optional[ValidationResult] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.schema = schema
        self.dxf_path = dxf_path
        self.raw_json = raw_json
        self.validation = validation
        self.error = error

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "dxf_path": str(self.dxf_path) if self.dxf_path else None,
            "schema": self.schema.model_dump() if self.schema else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "error": self.error,
        }


class DrawingGenerator:
    """AI 도면 생성기."""

    def __init__(self, llm=None, max_retries: int = 2):
        """
        Args:
            llm: LangChain LLM 인스턴스 (없으면 자동 로드)
            max_retries: 검증 실패 시 재시도 횟수
        """
        self.llm = llm
        self.max_retries = max_retries
        self._llm_loaded = False

    def _ensure_llm(self):
        """LLM 인스턴스 로드."""
        if self.llm is None and not self._llm_loaded:
            try:
                from packages.llm.src.config import get_llm
                self.llm = get_llm()
                self._llm_loaded = True
            except Exception as e:
                logger.error("LLM 로드 실패: %s", e)
                raise RuntimeError(f"LLM을 로드할 수 없습니다: {e}")

    def _extract_json(self, text: str) -> str:
        """LLM 응답에서 JSON 추출."""
        # 코드 블록에서 추출
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if code_block:
            return code_block.group(1).strip()

        # JSON 객체 직접 찾기
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            return json_match.group(0)

        return text.strip()

    def _call_llm(self, prompt: str, system: str = None) -> str:
        """LLM 호출."""
        self._ensure_llm()

        messages = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))

        response = self.llm.invoke(messages)
        return response.content

    async def generate(
        self,
        user_request: str,
        context: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> GenerationResult:
        """
        새 도면 생성.

        Args:
            user_request: 사용자 요청
            context: RAG 검색 컨텍스트 (선택)
            output_path: DXF 저장 경로 (선택)

        Returns:
            GenerationResult
        """
        logger.info("도면 생성 시작: %s", user_request[:50])

        system_prompt = GenerationPrompts.system_prompt()
        generate_prompt = GenerationPrompts.generate_prompt(user_request, context)

        for attempt in range(self.max_retries + 1):
            try:
                # LLM 호출
                raw_response = self._call_llm(generate_prompt, system_prompt)
                raw_json = self._extract_json(raw_response)

                # 검증
                validation = validate_full(raw_json)
                if not validation:
                    if attempt < self.max_retries:
                        # 재시도 프롬프트에 오류 피드백 추가
                        generate_prompt = f"""이전 시도에서 오류가 발생했습니다:
{chr(10).join(validation.errors)}

다시 시도하세요.

원래 요청: {user_request}

{GenerationPrompts.generate_prompt(user_request, context)}"""
                        logger.warning("검증 실패, 재시도 %d/%d", attempt + 1, self.max_retries)
                        continue
                    else:
                        return GenerationResult(
                            success=False,
                            raw_json=raw_json,
                            validation=validation,
                            error="검증 실패: " + ", ".join(validation.errors),
                        )

                # 스키마 파싱
                schema = SchemaValidator.parse(raw_json)
                if not schema:
                    return GenerationResult(success=False, error="스키마 파싱 실패")

                # DXF 생성
                dxf_path = None
                if output_path or True:  # 항상 DXF 생성
                    dxf_path = await self._generate_dxf(schema, output_path)

                return GenerationResult(
                    success=True,
                    schema=schema,
                    dxf_path=dxf_path,
                    raw_json=raw_json,
                    validation=validation,
                )

            except Exception as e:
                logger.exception("생성 중 오류: %s", e)
                if attempt == self.max_retries:
                    return GenerationResult(success=False, error=str(e))

        return GenerationResult(success=False, error="알 수 없는 오류")

    async def modify(
        self,
        user_request: str,
        current_schema: DrawingSchema,
        output_path: Optional[Path] = None,
    ) -> GenerationResult:
        """
        기존 도면 수정.

        Args:
            user_request: 수정 요청
            current_schema: 현재 스키마
            output_path: DXF 저장 경로

        Returns:
            GenerationResult
        """
        logger.info("도면 수정 시작: %s", user_request[:50])

        current_json = current_schema.model_dump_json(indent=2)
        system_prompt = GenerationPrompts.system_prompt()
        modify_prompt = GenerationPrompts.modify_prompt(user_request, current_json)

        try:
            raw_response = self._call_llm(modify_prompt, system_prompt)
            raw_json = self._extract_json(raw_response)

            validation = validate_full(raw_json)
            if not validation:
                return GenerationResult(
                    success=False,
                    raw_json=raw_json,
                    validation=validation,
                    error="검증 실패: " + ", ".join(validation.errors),
                )

            schema = SchemaValidator.parse(raw_json)
            if not schema:
                return GenerationResult(success=False, error="스키마 파싱 실패")

            dxf_path = await self._generate_dxf(schema, output_path)

            return GenerationResult(
                success=True,
                schema=schema,
                dxf_path=dxf_path,
                raw_json=raw_json,
                validation=validation,
            )

        except Exception as e:
            logger.exception("수정 중 오류: %s", e)
            return GenerationResult(success=False, error=str(e))

    async def validate_with_llm(
        self,
        schema: DrawingSchema,
        user_request: str,
    ) -> dict:
        """LLM을 사용한 시맨틱 검증 (LLM as Judge)."""
        prompt = GenerationPrompts.validation_prompt(
            schema.model_dump_json(indent=2),
            user_request,
        )

        try:
            response = self._call_llm(prompt)
            result_json = self._extract_json(response)
            return json.loads(result_json)
        except Exception as e:
            logger.error("LLM 검증 실패: %s", e)
            return {"valid": False, "issues": [str(e)], "suggestions": []}

    async def _generate_dxf(
        self,
        schema: DrawingSchema,
        output_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """스키마에서 DXF 생성."""
        try:
            from packages.dxf.src import DxfGenerator

            generator = DxfGenerator()

            # 도곽
            if schema.border:
                generator.add_border(
                    schema.border.width,
                    schema.border.height,
                    schema.border.margin,
                    schema.border.title_block,
                )

            # 축선
            if schema.grid:
                generator.add_grid(
                    schema.grid.x_positions,
                    schema.grid.y_positions,
                    schema.grid.x_labels,
                    schema.grid.y_labels,
                )

            # 기둥
            if schema.columns:
                for col in schema.columns:
                    generator.add_columns(
                        [(col.position.x, col.position.y)],
                        (col.size.width, col.size.height),
                    )

            # 벽체
            if schema.walls:
                segments = [
                    ((w.start.x, w.start.y), (w.end.x, w.end.y), w.thickness)
                    for w in schema.walls
                ]
                generator.add_walls(segments)

            # 개구부
            for opening in schema.openings:
                generator.add_opening(
                    (opening.position.x, opening.position.y),
                    opening.width,
                    opening.type,
                )

            # 저장
            if output_path is None:
                from packages.storage.src.config import STORAGE_DERIVED_PATH
                import uuid
                output_path = STORAGE_DERIVED_PATH / f"generated_{uuid.uuid4().hex[:8]}.dxf"

            return generator.save(output_path)

        except Exception as e:
            logger.exception("DXF 생성 실패: %s", e)
            return None
