"""Database operations for semantic analysis."""
import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src import models
from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)


def extract_layer_names(tables: dict[str, Any] | None, entities: list[dict[str, Any]]) -> list[str]:
    """Extract layer names from tables or entities.

    Args:
        tables: Tables section dictionary
        entities: List of entities

    Returns:
        List of layer names
    """
    layers: list[str] = []

    # Try tables first
    if isinstance(tables, dict):
        layer_dict = tables.get("layer", {}).get("layers") if isinstance(tables.get("layer"), dict) else None
        if isinstance(layer_dict, dict):
            layers = [k for k in layer_dict.keys() if k]

    # Fallback to extracting from entities
    if not layers:
        seen = set()
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            name = ent.get("layer") or ent.get("layerName")
            if name and name not in seen:
                seen.add(name)
                layers.append(str(name))

    return layers


async def load_raw_data(file_id: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Load raw parsed DXF data from database.

    Args:
        file_id: File UUID

    Returns:
        Tuple of (entities, blocks, tables)

    Raises:
        RuntimeError: If parse sections not found
    """
    async with SessionLocal() as session:
        section_row = await session.get(models.DxfParseSection, file_id)
        if not section_row:
            raise RuntimeError(f"raw db가 없습니다: file_id={file_id}")

        tables = section_row.tables if isinstance(section_row.tables, dict) else {}
        blocks = section_row.blocks if isinstance(section_row.blocks, dict) else {}
        entities = section_row.entities if isinstance(section_row.entities, list) else []

        return entities, blocks, tables


async def save_semantic_objects(file_id: str, records: list[dict[str, Any]]) -> None:
    """Save semantic objects to database.

    Args:
        file_id: File UUID
        records: List of semantic record dictionaries

    Raises:
        SQLAlchemyError: If database operation fails
    """
    async with SessionLocal() as session:
        try:
            # Delete existing semantic objects
            await session.execute(
                text("DELETE FROM semantic_objects WHERE file_id = :file_id"),
                {"file_id": file_id}
            )

            # Insert new records
            if records:
                # Serialize properties to JSON
                for rec in records:
                    if "properties" not in rec or rec["properties"] is None:
                        rec["properties"] = {}
                    rec["properties"] = json.dumps(rec["properties"], ensure_ascii=False)

                await session.execute(
                    text("""
                        INSERT INTO semantic_objects (file_id, kind, confidence, source_rule, properties, created_at)
                        VALUES (:file_id, :kind, :confidence, :source_rule, CAST(:properties AS JSONB), now())
                    """),
                    records,
                )

            await session.commit()
            logger.info("Semantic objects saved: file_id=%s, count=%d", file_id, len(records))

        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("Semantic objects save failed: %s", exc)
            raise


async def update_file_stats(file_id: str, layer_count: int, entity_count: int) -> None:
    """Update file statistics and log conversion success.

    Args:
        file_id: File UUID
        layer_count: Number of layers
        entity_count: Number of entities
    """
    async with SessionLocal() as session:
        try:
            # Update files table
            await session.execute(
                text("""
                    UPDATE files
                    SET layer_count = :layers, entity_count = :entities
                    WHERE id = :file_id
                """),
                {
                    "layers": layer_count,
                    "entities": entity_count,
                    "file_id": file_id,
                },
            )

            # Log conversion success
            await session.execute(
                text("""
                    INSERT INTO conversion_logs (file_id, status, started_at, finished_at, layer_count, entity_count, message)
                    VALUES (:file_id, 'success', now(), now(), :layers, :entities, :msg)
                """),
                {
                    "file_id": file_id,
                    "layers": layer_count,
                    "entities": entity_count,
                    "msg": "parse2: rule-based semantic build",
                },
            )

            await session.commit()

        except SQLAlchemyError as exc:
            await session.rollback()
            logger.exception("File stats update failed: %s", exc)
            raise
