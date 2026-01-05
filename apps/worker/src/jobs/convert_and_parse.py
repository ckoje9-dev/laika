"""DWG -> DXF 변환 후 바로 1차 파싱까지 수행하는 파이프라인 잡."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src import models
from packages.db.src.session import SessionLocal
from . import dwg_to_dxf, dxf_parse

logger = logging.getLogger(__name__)


async def run(file_id: str) -> None:
    """단일 file_id에 대해 변환과 파싱을 연속 수행한다."""
    async with SessionLocal() as session:
        file_row = await session.get(models.File, file_id)
        if not file_row:
            logger.error("convert_and_parse: file not found (%s)", file_id)
            return
        src = Path(file_row.path_original) if file_row.path_original else None
        if not src or not src.exists():
            logger.error("convert_and_parse: path_original 없거나 존재하지 않음 (%s)", file_id)
            return

    # 1) 변환 (이미 변환된 경우 dwg_to_dxf.run이 path_dxf를 덮어쓸 수 있음)
    try:
        await dwg_to_dxf.run(src=src, file_id=file_id)
    except Exception:
        logger.exception("convert_and_parse: 변환 실패 file_id=%s", file_id)
        return

    # 2) 파싱
    try:
        await dxf_parse.run(file_id=file_id)
    except Exception:
        logger.exception("convert_and_parse: 파싱 실패 file_id=%s", file_id)
        # 실패 로그는 dxf_parse 내부에서 기록됨
        return

    # 3) 성공 로그 추가(변환/파싱 성공 시점 기록)
    async with SessionLocal() as session:
        try:
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, message)
                    values (:file_id, 'success', now(), now(), 'convert+parse completed')
                    """
                ),
                {"file_id": file_id},
            )
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.warning("convert_and_parse: 완료 로그 기록 실패 file_id=%s", file_id)
