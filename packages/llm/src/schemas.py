"""인덱싱용 스키마."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class IndexItem:
    project_id: str
    version_id: str | None
    file_id: str | None
    kind: str  # project_meta, drawing_stats, semantic_summary 등
    text: str
    metadata: Mapping[str, Any]
