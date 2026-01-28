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


async def _build_sql_context(
    project_id: str,
    reference_file_ids: Optional[list[str]] = None,
) -> str:
    """SQL DB에서 파싱된 도면 데이터를 조회하여 LLM 컨텍스트를 구성한다.

    Args:
        project_id: 프로젝트 ID (reference_file_ids가 없을 때 전체 파일 조회)
        reference_file_ids: 특정 파일 ID 목록 (지정 시 해당 파일만 컨텍스트에 포함)
    """
    import json

    parts = []

    async with SessionLocal() as session:
        from sqlalchemy import select as sa_select

        if reference_file_ids:
            # 지정된 파일 ID로 직접 조회
            file_ids = reference_file_ids
            for file_id in file_ids:
                file = await session.get(models.File, file_id)
                if file:
                    parts.append(f"[참조 파일] id={file_id}, type={file.type}, layers={file.layer_count or 0}, entities={file.entity_count or 0}")
        else:
            # 프로젝트의 모든 파일 조회
            versions_result = await session.execute(
                sa_select(models.Version).where(models.Version.project_id == project_id)
            )
            versions = versions_result.scalars().all()

            file_ids = []
            for version in versions:
                files_result = await session.execute(
                    sa_select(models.File).where(models.File.version_id == version.id)
                )
                files = files_result.scalars().all()
                for f in files:
                    file_ids.append(str(f.id))
                    parts.append(f"[파일] type={f.type}, layers={f.layer_count or 0}, entities={f.entity_count or 0}")

        if not file_ids:
            return ""

        # 2. dxf_parse_sections에서 레이어/블록 구조 조회
        for file_id in file_ids[:5]:  # 최대 5개 파일
            sections = await session.get(models.DxfParseSection, file_id)
            if not sections:
                continue

            # 레이어 목록
            if sections.tables and isinstance(sections.tables, dict):
                layer_dict = sections.tables.get("layer", {})
                if isinstance(layer_dict, dict):
                    layers = layer_dict.get("layers", {})
                    if isinstance(layers, dict):
                        layer_names = list(layers.keys())[:30]
                        parts.append(f"[레이어 목록] {', '.join(layer_names)}")

            # 블록 목록
            if sections.blocks and isinstance(sections.blocks, dict):
                block_names = list(sections.blocks.keys())[:20]
                parts.append(f"[블록 목록] {', '.join(block_names)}")

            # 엔티티 타입 분포
            if sections.entities and isinstance(sections.entities, list):
                type_counts = {}
                for ent in sections.entities:
                    if isinstance(ent, dict):
                        t = ent.get("type", "unknown")
                        type_counts[t] = type_counts.get(t, 0) + 1
                type_summary = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:10])
                parts.append(f"[엔티티 분포] {type_summary}")

        # 3. semantic_objects에서 시맨틱 정보 조회
        for file_id in file_ids[:5]:
            sem_result = await session.execute(
                sa_select(models.SemanticObject).where(
                    models.SemanticObject.file_id == file_id
                )
            )
            sem_objects = sem_result.scalars().all()

            if not sem_objects:
                continue

            by_kind = {}
            for obj in sem_objects:
                by_kind.setdefault(obj.kind, []).append(obj)

            for kind, objs in by_kind.items():
                props_sample = []
                for obj in objs[:3]:  # 종류별 최대 3개 샘플
                    if obj.properties and isinstance(obj.properties, dict):
                        props_sample.append(obj.properties)

                parts.append(f"[시맨틱 {kind}] 개수={len(objs)}")
                if props_sample:
                    parts.append(f"  샘플: {json.dumps(props_sample[:2], ensure_ascii=False, default=str)[:500]}")

    return "\n".join(parts)


async def run_ai_generation(
    prompt: str,
    project_id: Optional[str] = None,
    template_data: Optional[dict[str, Any]] = None,
    conversation_history: Optional[list[dict]] = None,
    output_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    AI 기반 도면 생성 파이프라인.

    Args:
        prompt: 사용자 요청
        project_id: 프로젝트 ID
        template_data: 템플릿 파일의 파싱 데이터 (선택적)
        conversation_history: 대화 히스토리
        output_path: 출력 경로

    Returns:
        생성 결과 (schema, validation, dxf_path, message)
    """
    import json
    from packages.generation.src.generator import DrawingGenerator

    logger.info("AI 도면 생성 시작: %s", prompt[:50])

    generator = DrawingGenerator()

    # 템플릿 데이터가 있으면 컨텍스트로 구성
    context = None
    if template_data:
        parts = []
        parts.append(f"[템플릿 파일] file_id={template_data.get('file_id')}")

        # 레이어 정보
        layers = template_data.get("layers", {})
        if layers:
            layer_names = list(layers.keys())[:30] if isinstance(layers, dict) else []
            parts.append(f"[레이어 목록] {', '.join(layer_names)}")

        # 블록 정보
        blocks = template_data.get("blocks", {})
        if blocks:
            block_names = [k for k in blocks.keys() if not k.startswith("*")][:20]
            parts.append(f"[블록 목록] {', '.join(block_names)}")

        # 엔티티 샘플
        entities = template_data.get("entities_sample", [])
        if entities:
            type_counts = {}
            for ent in entities:
                if isinstance(ent, dict):
                    t = ent.get("type", "unknown")
                    type_counts[t] = type_counts.get(t, 0) + 1
            type_summary = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:10])
            parts.append(f"[엔티티 분포 (샘플)] {type_summary}")

        context = "\n".join(parts)
        logger.info("템플릿 컨텍스트 구성 완료: %d자", len(context))

    # 도면 생성
    result = await generator.generate(
        user_request=prompt,
        context=context,
        conversation_history=conversation_history or [],
        output_path=Path(output_path) if output_path else None,
    )

    return {
        "success": result.success,
        "schema": result.schema.model_dump() if result.schema else None,
        "validation": result.validation.to_dict() if result.validation else None,
        "dxf_path": str(result.dxf_path) if result.dxf_path else None,
        "message": "도면을 생성했습니다." if result.success else result.error,
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
