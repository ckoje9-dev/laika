"""DWG 업로드 감지 후 ODA 변환 실행 잡."""
import logging

logger = logging.getLogger(__name__)


async def run() -> None:
    # TODO: 큐/이벤트에서 작업 수신 후 ODA 실행, 로그/메타데이터 저장
    logger.info("dwg_to_dxf job stub")
