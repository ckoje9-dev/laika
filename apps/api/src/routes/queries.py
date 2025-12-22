"""RAG 기반 질의응답 라우터."""
from fastapi import APIRouter

router = APIRouter(tags=["queries"])


@router.post("/")
async def ask_question():
    # TODO: RAG 파이프라인 연동 후 답변 반환
    return {"answer": "준비 중", "sources": []}
