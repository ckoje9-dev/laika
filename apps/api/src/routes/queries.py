"""RAG 기반 질의응답 라우터."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from langchain_classic.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

from packages.db.src.session import SessionLocal
from packages.db.src import models
from packages.llm.src.config import get_llm, get_embeddings
from packages.llm.src.indexer import build_default_indexer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["queries"])


class QuestionRequest(BaseModel):
    question: str
    project_id: Optional[str] = None
    top_k: int = 5


class SourceDoc(BaseModel):
    content: str
    kind: str
    file_id: Optional[str] = None


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceDoc]
    confidence: Optional[float] = None


# RAG 프롬프트 템플릿
RAG_PROMPT_TEMPLATE = """당신은 건축 도면 분석 전문가입니다.
주어진 컨텍스트를 바탕으로 질문에 답변해주세요.
컨텍스트에 없는 정보는 "정보가 없습니다"라고 답변하세요.

컨텍스트:
{context}

질문: {question}

답변:"""


@router.post("/", response_model=AnswerResponse)
async def ask_question(req: QuestionRequest):
    """RAG 기반 질의응답."""
    try:
        indexer = build_default_indexer()
        llm = get_llm()

        # 프로젝트 필터링 (선택적)
        search_kwargs = {"k": req.top_k}
        if req.project_id:
            search_kwargs["filter"] = {"project_id": req.project_id}

        retriever = indexer.store.as_retriever(search_kwargs=search_kwargs)

        prompt = PromptTemplate(
            template=RAG_PROMPT_TEMPLATE,
            input_variables=["context", "question"]
        )

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": prompt}
        )

        result = qa_chain({"query": req.question})

        # 소스 문서 변환
        sources = []
        for doc in result.get("source_documents", []):
            sources.append(SourceDoc(
                content=doc.page_content[:200],
                kind=doc.metadata.get("kind", "unknown"),
                file_id=doc.metadata.get("file_id")
            ))

        answer = result.get("result", "답변을 생성할 수 없습니다.")

        # Q&A 히스토리 저장
        if req.project_id:
            try:
                async with SessionLocal() as session:
                    qa_record = models.QaHistory(
                        project_id=req.project_id,
                        question=req.question,
                        answer=answer,
                        sources=[s.model_dump() for s in sources]
                    )
                    session.add(qa_record)
                    await session.commit()
            except Exception as e:
                logger.warning("Q&A 히스토리 저장 실패: %s", e)

        return AnswerResponse(
            answer=answer,
            sources=sources
        )

    except Exception as e:
        logger.exception("질의응답 처리 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{project_id}")
async def get_qa_history(project_id: str, limit: int = 20):
    """프로젝트별 Q&A 히스토리 조회."""
    from sqlalchemy import select

    async with SessionLocal() as session:
        result = await session.execute(
            select(models.QaHistory)
            .where(models.QaHistory.project_id == project_id)
            .order_by(models.QaHistory.created_at.desc())
            .limit(limit)
        )
        records = result.scalars().all()

        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "sources": r.sources,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
