"""Database operations for parser."""
import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src import models
from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)


async def resolve_file_path(file_id: str) -> Optional[Path]:
    """Resolve DXF file path from database.

    Args:
        file_id: UUID of the file

    Returns:
        Path to DXF file, or None if not found
    """
    async with SessionLocal() as session:
        file_row = await session.get(models.File, file_id)
        if not file_row:
            logger.error("file not found: %s", file_id)
            return None

        # Use path_dxf if available, otherwise fallback to path_original
        if not file_row.path_dxf and file_row.path_original:
            file_row.path_dxf = file_row.path_original

        if not file_row.path_dxf:
            logger.error("DXF 경로가 없습니다. file_id=%s", file_id)
            return None

        return Path(file_row.path_dxf)


async def save_parse_results(file_id: str, json_path: Path) -> None:
    """Save parsing results to database.

    Args:
        file_id: UUID of the file
        json_path: Path to parsed JSON file
    """
    try:
        with json_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        logger.warning("JSON 로드 실패: %s", json_path)
        data = {}

    # Extract sections and entities
    sections = data.get("sections") if isinstance(data, dict) else {}
    if not isinstance(sections, dict):
        sections = {}

    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, list):
        entities = []

    # Extract layer names
    layer_names = set()
    tables = sections.get("tables") if isinstance(sections, dict) else None
    if isinstance(tables, dict):
        raw_layers = (
            tables.get("layer", {}).get("layers")
            or tables.get("layers")
            or tables.get("layer")
        )
        if isinstance(raw_layers, dict):
            raw_layers = raw_layers.get("layers") or list(raw_layers.values())
        if isinstance(raw_layers, list):
            for l in raw_layers:
                name = l.get("name") if isinstance(l, dict) else l
                if name:
                    layer_names.add(str(name))

    # Fallback: extract from entities
    if not layer_names:
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            layer = ent.get("layer") or ent.get("layerName")
            if layer:
                layer_names.add(str(layer))

    # Save to database
    async with SessionLocal() as session:
        try:
            # Delete existing parse sections
            await session.execute(
                text("DELETE FROM dxf_parse_sections WHERE file_id = :file_id"),
                {"file_id": file_id}
            )

            # Insert new parse sections
            session.add(
                models.DxfParseSection(
                    file_id=file_id,
                    header=sections.get("header"),
                    classes=sections.get("classes"),
                    tables=sections.get("tables"),
                    blocks=sections.get("blocks"),
                    entities=entities,
                    objects=sections.get("objects"),
                    thumbnail=sections.get("thumbnail"),
                )
            )

            # Update file statistics
            await session.execute(
                text("""
                    UPDATE files
                    SET layer_count = :layers, entity_count = :entities
                    WHERE id = :file_id
                """),
                {
                    "layers": len(layer_names),
                    "entities": len(entities),
                    "file_id": file_id,
                },
            )

            # Log conversion success
            await session.execute(
                text("""
                    INSERT INTO conversion_logs (file_id, status, started_at, finished_at, layer_count, entity_count, message)
                    VALUES (:file_id, 'success', now(), now(), :layers, :entities, :path)
                """),
                {
                    "file_id": file_id,
                    "layers": len(layer_names),
                    "entities": len(entities),
                    "path": str(json_path),
                },
            )

            await session.commit()
            logger.info("DB 저장 완료: file_id=%s, layers=%d, entities=%d", file_id, len(layer_names), len(entities))

        except SQLAlchemyError:
            await session.rollback()
            logger.exception("parse1 DB 적재 실패: file_id=%s", file_id)
            raise
