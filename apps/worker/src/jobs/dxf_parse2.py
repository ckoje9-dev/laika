"""DXF 2차 파싱: 현재 비활성화 상태 (스텁)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)

STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))


async def run(file_id: str | None = None) -> None:
    """2차 파싱 비활성: 호출되면 성공 로그만 남기고 종료."""
    if not file_id:
        logger.error("file_id가 필요합니다.")
        return

    async with SessionLocal() as session:
        try:
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, message)
                    values (:file_id, 'success', now(), now(), 'parse2-disabled')
                    """
                ),
                {"file_id": file_id},
            )
            await session.commit()
            logger.info("2차 파싱 비활성: file_id=%s", file_id)
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("2차 파싱 스텁 처리 중 오류: %s", e)
