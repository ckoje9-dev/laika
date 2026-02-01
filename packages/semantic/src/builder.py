"""Semantic record construction."""
from typing import Any, Iterable

from .matchers import match_rule
from .detectors import border, axis, column, wall, room


def build_semantic_records(
    entities: Iterable[dict[str, Any]],
    file_id: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build basic semantic records from entities using rules.

    Args:
        entities: List of DXF entities
        file_id: File UUID
        rules: List of classification rules

    Returns:
        List of semantic record dictionaries
    """
    records: list[dict[str, Any]] = []

    for ent in entities:
        if not isinstance(ent, dict):
            continue

        kind, source_rule = match_rule(ent, rules)
        if not kind:
            continue

        records.append({
            "file_id": file_id,
            "kind": kind,
            "confidence": None,
            "source_rule": source_rule,
            "properties": ent,
        })

    return records


def build_all_records(
    file_id: str,
    entities: list[dict[str, Any]],
    blocks: dict[str, Any],
    tables: dict[str, Any],
    selections: dict[str, list[str]] | None,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build all semantic objects including basic and specialized detectors.

    Args:
        file_id: File UUID
        entities: List of DXF entities
        blocks: Block definitions dictionary
        tables: Tables dictionary
        selections: User selections
        rules: Classification rules

    Returns:
        Combined list of all semantic records
    """
    # 1. Basic rule-based matching
    basic_records = build_semantic_records(entities, file_id, rules)

    # 2. Specialized object detection
    borders = border.build_border_records(file_id, blocks, entities, selections)
    axis_summaries = axis.build_axis_summary_records(file_id, borders, entities, selections)
    columns = column.build_column_records(file_id, axis_summaries, entities, selections)
    walls = wall.build_wall_records(file_id, borders, entities, selections)
    rooms = room.build_room_records(file_id, walls, entities)

    return basic_records + borders + axis_summaries + columns + walls + rooms
