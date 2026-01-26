"""1차 DXF 파싱: Node dxf-parser를 호출해 섹션/엔티티 JSON을 생성한다."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from packages.parser.src import node_parser, db_adapter
from packages.storage.src.config import STORAGE_DERIVED_PATH

logger = logging.getLogger(__name__)


async def run(file_id: Optional[str] = None, src: Optional[Path] = None, output_path: Optional[Path] = None) -> Optional[Path]:
    """DXF를 1차 파싱해 JSON을 생성한다."""
    if isinstance(src, str):
        src = Path(src)
    if isinstance(output_path, str):
        output_path = Path(output_path)

    # Resolve source file path
    if file_id:
        src_path = await db_adapter.resolve_file_path(file_id)
    else:
        src_path = src

    if src_path is None:
        logger.error("Source path could not be resolved")
        return None

    # Determine output path
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)
    out_path = output_path or STORAGE_DERIVED_PATH / f"{src_path.stem}_parse1.json"

    try:
        # Parse DXF using Node.js subprocess
        await node_parser.parse_dxf(src_path, out_path)
        logger.info("1차 파싱 완료: %s -> %s", src_path, out_path)

        # Save results to database
        if file_id:
            await db_adapter.save_parse_results(file_id, out_path)

            # Log success status
            from packages.db.src.session import SessionLocal
            async with SessionLocal() as session:
                await session.execute(
                    text("INSERT INTO conversion_logs (file_id, status, started_at, finished_at, message) VALUES (:file_id, 'success', now(), now(), :msg)"),
                    {"file_id": file_id, "msg": "parse1 completed successfully"},
                )
                await session.commit()

        return out_path

    except Exception as e:
        logger.exception("1차 파싱 실패: %s", src_path)

        # Log failure
        if file_id:
            from packages.db.src.session import SessionLocal
            async with SessionLocal() as session:
                await session.execute(
                    text("INSERT INTO conversion_logs (file_id, status, started_at, finished_at, message) VALUES (:file_id, 'failed', now(), now(), :msg)"),
                    {"file_id": file_id, "msg": f"parse1 failed: {str(e)}"},
                )
                await session.commit()

        return None
