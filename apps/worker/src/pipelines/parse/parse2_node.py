"""DXF 2차 파싱: raw DB 조회 + rule-based 정제 + semantic DB 적재."""
from __future__ import annotations

import logging
from typing import Any, Optional

from packages.semantic.src import rules, matchers, builder, db_adapter

logger = logging.getLogger(__name__)


async def run(
    file_id: Optional[str] = None,
    selections: dict[str, list[str]] | None = None,
    rules_override: list[dict[str, Any]] | None = None,
) -> None:
    """raw DB를 기반으로 rule-based 정제 후 semantic_objects에 저장."""
    if not file_id:
        logger.error("file_id가 없어 2차 파싱을 건너뜁니다.")
        return

    # Load raw parsed data from DB
    try:
        entities, blocks, tables = await db_adapter.load_raw_data(file_id)
    except RuntimeError as e:
        logger.error(str(e))
        return

    # Extract layer names for statistics
    layers = db_adapter.extract_layer_names(tables, entities)
    entity_count = len(entities)

    # Determine effective rules
    effective_rules = rules_override or matchers.rules_from_selections(selections) or rules.DEFAULT_RULES

    # Log selection info
    if selections:
        logger.info(
            "parse2 selections: border=%s axis=%s ccol=%s",
            selections.get("basic-border-block"),
            selections.get("struct-axis-layer"),
            selections.get("struct-ccol-layer"),
        )

        # Log diagnostic info
        if selections.get("basic-border-block"):
            block_name = str(selections.get("basic-border-block")[0])
            insert_hits = [
                e for e in entities
                if isinstance(e, dict) and e.get("type") == "INSERT"
                and str(e.get("name") or "").upper() == block_name.upper()
            ]
            logger.info("border block=%s blocks=%s inserts=%s", block_name, len(blocks), len(insert_hits))

        if selections.get("struct-axis-layer"):
            axis_layers = {str(v).upper() for v in selections.get("struct-axis-layer") or [] if v}
            axis_hits = [
                e for e in entities
                if isinstance(e, dict) and e.get("type") in ("LINE", "LWPOLYLINE")
                and str(e.get("layer") or e.get("layerName") or "").upper() in axis_layers
            ]
            logger.info("axis layers=%s hits=%s", list(axis_layers), len(axis_hits))

        if selections.get("struct-ccol-layer"):
            col_layers = {str(v).upper() for v in selections.get("struct-ccol-layer") or [] if v}
            col_hits = [
                e for e in entities
                if isinstance(e, dict)
                and str(e.get("layer") or e.get("layerName") or "").upper() in col_layers
            ]
            logger.info("column layers=%s hits=%s", list(col_layers), len(col_hits))

    # Build all semantic records
    all_records = builder.build_all_records(
        file_id=file_id,
        entities=entities,
        blocks=blocks,
        tables=tables,
        selections=selections,
        rules=effective_rules
    )

    # Save to database
    try:
        await db_adapter.save_semantic_objects(file_id, all_records)
        await db_adapter.update_file_stats(file_id, len(layers), entity_count)
        logger.info("2차 파싱 완료: file_id=%s records=%d", file_id, len(all_records))
    except Exception as exc:
        logger.exception("2차 파싱 실패: %s", exc)
        raise
