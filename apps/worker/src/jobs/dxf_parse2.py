"""DXF 2차 파싱/정규화 잡: 룰 기반으로 엔티티 속성 갱신."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select, update, text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src.session import SessionLocal
from packages.db.src import models

logger = logging.getLogger(__name__)

DXF_RULES_PATH = Path(os.getenv("DXF_RULES_PATH", "config/dxf_rules.json"))


def _load_rules() -> dict[str, Any]:
    if not DXF_RULES_PATH.exists():
        logger.warning("DXF 룰 파일을 찾을 수 없습니다: %s", DXF_RULES_PATH)
        return {}
    try:
        with DXF_RULES_PATH.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as e:  # pragma: no cover
        logger.warning("DXF 룰 파일 로드 실패: %s", e)
        return {}


def _classify_layer(layer: str | None, color_index: int | None, rules: list[dict[str, Any]]) -> str | None:
    if not layer or not rules:
        return None
    lname = layer.lower()
    for rule in rules:
        contains = rule.get("contains") or []
        color = rule.get("color")
        if any(key in lname for key in contains) and (color is None or color == color_index):
            return rule.get("tag")
    return None


def _match_layer_definition(layer: str | None, color_index: int | None, defs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not layer or not defs:
        return None
    for item in defs:
        name = item.get("name")
        if not name or name.lower() != layer.lower():
            continue
        color = item.get("color")
        if color is not None and color_index is not None and int(color) != int(color_index):
            continue
        return {"name": name, "color": color, "description": item.get("description")}
    return None


async def run(file_id: str | None = None) -> None:
    """룰 기반 2차 파싱: 레이어 규칙 등을 적용해 properties.classification을 갱신."""
    if not file_id:
        logger.error("file_id가 필요합니다.")
        return

    rules = _load_rules()
    layer_rules = rules.get("layer_rules") or []
    layer_defs = rules.get("layer_definitions") or []
    if not layer_rules:
        logger.warning("레이어 룰이 비어 있습니다. 2차 파싱 없이 종료합니다.")
        # 정의만으로도 덮어쓸 수 있으므로 계속 진행

    async with SessionLocal() as session:
        try:
            stmt = select(
                models.DxfEntityRaw.id,
                models.DxfEntityRaw.layer,
                models.DxfEntityRaw.properties,
            ).where(models.DxfEntityRaw.file_id == file_id)
            rows = await session.execute(stmt)
            rows = rows.all()
            if not rows:
                logger.warning("엔티티가 없습니다. file_id=%s", file_id)
                return

            for rid, layer, props in rows:
                props = props or {}
                classification = _classify_layer(layer, props.get("color_index"), layer_rules) if layer_rules else None
                if classification:
                    props["classification"] = classification
                layer_def = _match_layer_definition(layer, props.get("color_index"), layer_defs) if layer_defs else None
                if layer_def:
                    props["layer_definition"] = layer_def
                await session.execute(
                    update(models.DxfEntityRaw)
                    .where(models.DxfEntityRaw.id == rid)
                    .values(properties=props)
                )

            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, message)
                    values (:file_id, 'success', now(), now(), 'parse2')
                    """
                ),
                {"file_id": file_id},
            )
            await session.commit()
            logger.info("2차 파싱 완료: file_id=%s (entities=%s)", file_id, len(rows))
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("2차 파싱 중 오류: %s", e)
            raise
