"""업로드 초기화 및 변환 상태 조회 라우터."""
from fastapi import APIRouter

router = APIRouter(tags=["uploads"])


@router.post("/init")
async def init_upload():
    # TODO: 서명 URL 발급 및 파일 메타데이터 생성
    return {"upload_url": "signed-url-placeholder", "file_id": "file-id-placeholder"}


@router.get("/{file_id}/status")
async def get_upload_status(file_id: str):
    # TODO: 변환/파싱 상태 조회
    return {"file_id": file_id, "status": "pending"}
