"""DXF 생성 파이프라인."""
import logging
from pathlib import Path
from typing import Optional, Any

from sqlalchemy import select

from packages.db.src.session import SessionLocal
from packages.db.src import models
from packages.dxf.src import DxfGenerator
from packages.storage.src.config import STORAGE_DERIVED_PATH

logger = logging.getLogger(__name__)


async def _load_semantic_objects(session, file_id: str) -> list[dict[str, Any]]:
    """시맨틱 객체 로드."""
    result = await session.execute(
        select(models.SemanticObject).where(
            models.SemanticObject.file_id == file_id
        )
    )
    objects = result.scalars().all()
    return [
        {
            "kind": obj.kind,
            "properties": obj.properties or {},
            "source_rule": obj.source_rule,
        }
        for obj in objects
    ]


async def run(
    file_id: Optional[str] = None,
    output_path: Optional[str] = None,
    from_prompt: Optional[str] = None,
    semantic_objects: Optional[list[dict[str, Any]]] = None,
) -> Optional[Path]:
    """
    DXF 생성 파이프라인.

    Args:
        file_id: 기존 파일의 시맨틱 객체 기반 생성 시
        output_path: 출력 경로 (미지정 시 자동 생성)
        from_prompt: LLM 프롬프트 기반 생성 시 (향후 구현)
        semantic_objects: 직접 전달된 시맨틱 객체 리스트

    Returns:
        생성된 DXF 파일 경로
    """
    logger.info("DXF 생성 시작")

    generator = DxfGenerator()

    # 1. 시맨틱 객체 기반 생성
    if file_id:
        async with SessionLocal() as session:
            objects = await _load_semantic_objects(session, file_id)
            if not objects:
                logger.warning("시맨틱 객체가 없습니다: %s", file_id)
                return None

            logger.info("시맨틱 객체 %d개로 DXF 생성", len(objects))
            generator.from_semantic_objects(objects)

            # 출력 경로 결정
            if not output_path:
                output_path = STORAGE_DERIVED_PATH / f"{file_id}_generated.dxf"

    # 2. 직접 전달된 시맨틱 객체 사용
    elif semantic_objects:
        logger.info("전달된 시맨틱 객체 %d개로 DXF 생성", len(semantic_objects))
        generator.from_semantic_objects(semantic_objects)

        if not output_path:
            output_path = STORAGE_DERIVED_PATH / "generated.dxf"

    # 3. LLM 프롬프트 기반 생성
    elif from_prompt:
        logger.info("프롬프트 기반 DXF 생성: %s", from_prompt[:50])
        result = await run_ai_generation(from_prompt, output_path=output_path)
        return result

        if not output_path:
            output_path = STORAGE_DERIVED_PATH / "prompt_generated.dxf"

    else:
        logger.error("file_id, semantic_objects, 또는 from_prompt 중 하나가 필요합니다.")
        return None

    # 저장
    output_path = Path(output_path)
    generator.save(output_path)
    logger.info("DXF 생성 완료: %s", output_path)

    return output_path


async def generate_from_template(
    template_name: str,
    params: dict[str, Any],
    output_path: Optional[str] = None,
) -> Optional[Path]:
    """
    템플릿 기반 DXF 생성.

    Args:
        template_name: 템플릿 이름 (grid, building_frame, etc.)
        params: 템플릿 파라미터
        output_path: 출력 경로

    Returns:
        생성된 DXF 파일 경로
    """
    logger.info("템플릿 기반 DXF 생성: %s", template_name)

    generator = DxfGenerator()

    if template_name == "grid":
        # 그리드 템플릿
        x_count = params.get("x_count", 4)
        y_count = params.get("y_count", 3)
        x_spacing = params.get("x_spacing", 7000)
        y_spacing = params.get("y_spacing", 7000)

        x_positions = [i * x_spacing for i in range(x_count)]
        y_positions = [i * y_spacing for i in range(y_count)]

        generator.add_grid(x_positions, y_positions)

    elif template_name == "building_frame":
        # 건물 골조 템플릿
        x_count = params.get("x_count", 4)
        y_count = params.get("y_count", 3)
        x_spacing = params.get("x_spacing", 7000)
        y_spacing = params.get("y_spacing", 7000)
        column_size = params.get("column_size", (600, 600))
        has_border = params.get("has_border", True)

        x_positions = [i * x_spacing for i in range(x_count)]
        y_positions = [i * y_spacing for i in range(y_count)]

        generator.add_grid(x_positions, y_positions)

        # 모든 교차점에 기둥
        column_positions = [(x, y) for x in x_positions for y in y_positions]
        generator.add_columns(column_positions, column_size)

        if has_border:
            width = max(x_positions) + 2000
            height = max(y_positions) + 2000
            generator.add_border(width, height)

    else:
        logger.error("알 수 없는 템플릿: %s", template_name)
        return None

    if not output_path:
        output_path = STORAGE_DERIVED_PATH / f"{template_name}_generated.dxf"

    output_path = Path(output_path)
    generator.save(output_path)
    logger.info("템플릿 DXF 생성 완료: %s", output_path)

    return output_path


async def run_ai_generation(
    prompt: str,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context: Optional[str] = None,
    output_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    AI 기반 도면 생성 파이프라인.

    Args:
        prompt: 사용자 요청
        project_id: 프로젝트 ID (RAG 컨텍스트용)
        session_id: 세션 ID (대화 기록용)
        context: 추가 컨텍스트
        output_path: 출력 경로

    Returns:
        생성 결과 (schema, validation, dxf_path)
    """
    from packages.generation.src.generator import DrawingGenerator

    logger.info("AI 도면 생성 시작: %s", prompt[:50])

    generator = DrawingGenerator()

    # RAG 컨텍스트 로드 (project_id가 있으면)
    rag_context = context
    if project_id and not context:
        try:
            from packages.llm.src.retriever import get_retriever
            retriever = get_retriever(project_id=project_id)
            docs = retriever.get_relevant_documents(prompt)
            if docs:
                rag_context = "\n\n".join([doc.page_content for doc in docs[:3]])
        except Exception as e:
            logger.warning("RAG 컨텍스트 로드 실패: %s", e)

    # 도면 생성
    result = await generator.generate(
        user_request=prompt,
        context=rag_context,
        output_path=Path(output_path) if output_path else None,
    )

    return {
        "success": result.success,
        "schema": result.schema.model_dump() if result.schema else None,
        "validation": result.validation.to_dict() if result.validation else None,
        "dxf_path": str(result.dxf_path) if result.dxf_path else None,
        "error": result.error,
    }


async def run_ai_modification(
    prompt: str,
    current_schema: dict[str, Any],
    output_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    AI 기반 도면 수정 파이프라인.

    Args:
        prompt: 수정 요청
        current_schema: 현재 스키마 JSON
        output_path: 출력 경로

    Returns:
        수정 결과 (schema, validation, dxf_path)
    """
    from packages.generation.src.generator import DrawingGenerator
    from packages.generation.src.schema import DrawingSchema

    logger.info("AI 도면 수정 시작: %s", prompt[:50])

    generator = DrawingGenerator()

    # 현재 스키마 파싱
    schema = DrawingSchema.model_validate(current_schema)

    # 도면 수정
    result = await generator.modify(
        user_request=prompt,
        current_schema=schema,
        output_path=Path(output_path) if output_path else None,
    )

    return {
        "success": result.success,
        "schema": result.schema.model_dump() if result.schema else None,
        "validation": result.validation.to_dict() if result.validation else None,
        "dxf_path": str(result.dxf_path) if result.dxf_path else None,
        "error": result.error,
    }
