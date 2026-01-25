"""시맨틱 객체 임베딩 생성 파이프라인."""
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.src.session import SessionLocal
from packages.db.src import models
from packages.llm.src.config import get_embeddings

logger = logging.getLogger(__name__)


def _generate_text_representation(obj: models.SemanticObject) -> str:
    """시맨틱 객체를 텍스트로 표현."""
    props = obj.properties or {}
    kind = obj.kind

    if kind == "border":
        bbox = props.get("bbox_world", {})
        width = bbox.get("xmax", 0) - bbox.get("xmin", 0)
        height = bbox.get("ymax", 0) - bbox.get("ymin", 0)
        return f"도곽(Title Block): 위치=({bbox.get('xmin')}, {bbox.get('ymin')}), 크기={width:.0f}x{height:.0f}"

    elif kind == "axis_summary":
        x_axes = props.get("x_axes", [])
        y_axes = props.get("y_axes", [])
        x_spacing = props.get("x_spacing", [])
        y_spacing = props.get("y_spacing", [])
        return f"축선 요약(Grid Summary): X축 {len(x_axes)}개 (간격: {x_spacing}), Y축 {len(y_axes)}개 (간격: {y_spacing})"

    elif kind == "concrete_column":
        center = props.get("center", {})
        col_type = props.get("column_type", "unknown")
        size = props.get("size", {})
        return f"콘크리트 기둥({col_type}): 중심=({center.get('x')}, {center.get('y')}), 크기={size.get('width', 0)}x{size.get('height', 0)}"

    elif kind == "axis":
        orientation = props.get("orientation", "unknown")
        label = props.get("label", "")
        return f"축선(Grid Line): {label}, 방향={orientation}"

    elif kind == "dimension":
        dim_type = props.get("type", "linear")
        value = props.get("value", "")
        return f"치수(Dimension): 타입={dim_type}, 값={value}"

    elif kind == "wall":
        length = props.get("length", 0)
        thickness = props.get("thickness", 0)
        return f"벽체(Wall): 길이={length}, 두께={thickness}"

    elif kind == "door":
        width = props.get("width", 0)
        return f"문(Door): 폭={width}"

    elif kind == "window":
        width = props.get("width", 0)
        height = props.get("height", 0)
        return f"창문(Window): 폭={width}, 높이={height}"

    else:
        # 기타 종류는 properties 일부 포함
        props_str = str(props)[:200] if props else ""
        return f"{kind}: {props_str}"


async def run(file_id: Optional[str] = None, batch_size: int = 100) -> None:
    """시맨틱 객체에 임베딩 생성."""
    if not file_id:
        logger.error("file_id가 필요합니다.")
        return

    logger.info("임베딩 생성 시작: %s", file_id)

    embeddings = get_embeddings()

    async with SessionLocal() as session:
        result = await session.execute(
            select(models.SemanticObject).where(
                models.SemanticObject.file_id == file_id
            )
        )
        objects = result.scalars().all()

        if not objects:
            logger.warning("시맨틱 객체가 없습니다: %s", file_id)
            return

        logger.info("임베딩 생성 대상: %d개", len(objects))

        # 배치 단위 처리
        for i in range(0, len(objects), batch_size):
            batch = objects[i:i + batch_size]
            texts = [_generate_text_representation(obj) for obj in batch]

            try:
                vectors = embeddings.embed_documents(texts)

                for obj, vector in zip(batch, vectors):
                    # pgvector 컬럼 업데이트 (raw SQL 사용)
                    await session.execute(
                        text(
                            "UPDATE semantic_objects SET embedding = :vector::vector "
                            "WHERE id = :id"
                        ),
                        {"vector": str(vector), "id": obj.id}
                    )

                await session.commit()
                logger.info("배치 완료: %d-%d / %d", i + 1, min(i + batch_size, len(objects)), len(objects))

            except Exception as e:
                logger.exception("배치 처리 실패: %s", e)
                await session.rollback()
                raise

    logger.info("임베딩 생성 완료: %s", file_id)
