"""DXF 파싱 파이프라인: 1차(Node dxf-parser) 파싱 + DB 적재."""
from pathlib import Path
from typing import Optional
import logging

from apps.worker.src.pipelines.parse import parse1_node

logger = logging.getLogger(__name__)


async def run(file_id: Optional[str] = None, src: Optional[Path] = None):
    """1차/2차 파싱을 순차 실행."""
    json_path = await parse1_node.run(file_id=file_id, src=src)
    if json_path is None:
        logger.error("1차 파싱 실패: file_id=%s", file_id)
        return None
    return json_path
