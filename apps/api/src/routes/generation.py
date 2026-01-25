"""AI 도면 생성 엔드포인트."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from packages.db.src.session import SessionLocal
from packages.db.src.models import GenerationSession, GenerationVersion, Project
from packages.generation.src import DrawingSchema

logger = logging.getLogger(__name__)
router = APIRouter(tags=["generation"])


class GenerateRequest(BaseModel):
    """도면 생성 요청."""
    project_id: str
    prompt: str
    session_id: Optional[str] = None


class ModifyRequest(BaseModel):
    """도면 수정 요청."""
    session_id: str
    prompt: str


class GenerateResponse(BaseModel):
    """도면 생성 응답."""
    session_id: str
    version_number: int
    schema: Optional[dict] = None
    validation: Optional[dict] = None
    dxf_path: Optional[str] = None


class SessionResponse(BaseModel):
    """세션 정보 응답."""
    id: str
    project_id: str
    title: Optional[str]
    status: str
    version_count: int
    created_at: str


@router.post("/generate", response_model=GenerateResponse)
async def generate_drawing(req: GenerateRequest) -> GenerateResponse:
    """새 도면 생성 또는 기존 세션에서 생성."""
    async with SessionLocal() as session:
        # 프로젝트 존재 확인
        project = await session.get(Project, req.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

        # 세션 생성 또는 조회
        if req.session_id:
            gen_session = await session.get(GenerationSession, req.session_id)
            if not gen_session:
                raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        else:
            gen_session = GenerationSession(
                project_id=req.project_id,
                title=req.prompt[:50] if req.prompt else "새 도면",
                status="active",
                conversation_history=[]
            )
            session.add(gen_session)
            await session.flush()

        # 버전 번호 계산
        version_count_result = await session.execute(
            select(GenerationVersion).where(
                GenerationVersion.session_id == str(gen_session.id)
            )
        )
        existing_versions = version_count_result.scalars().all()
        version_number = len(existing_versions) + 1

        # 도면 생성
        try:
            from apps.worker.src.pipelines.generate_dxf import run_ai_generation
            result = await run_ai_generation(
                prompt=req.prompt,
                project_id=req.project_id,
                session_id=str(gen_session.id) if gen_session else None,
            )
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("error", "생성 실패"))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("도면 생성 실패: %s", e)
            raise HTTPException(status_code=500, detail=f"도면 생성 실패: {str(e)}")

        # 버전 저장
        gen_version = GenerationVersion(
            session_id=str(gen_session.id),
            version_number=version_number,
            prompt=req.prompt,
            schema_json=result["schema"],
            validation_result=result["validation"],
            dxf_path=result.get("dxf_path")
        )
        session.add(gen_version)

        # 대화 히스토리 업데이트
        history = gen_session.conversation_history or []
        history.append({
            "role": "user",
            "content": req.prompt
        })
        history.append({
            "role": "assistant",
            "content": f"도면을 생성했습니다. (버전 {version_number})"
        })
        gen_session.conversation_history = history

        await session.commit()

        return GenerateResponse(
            session_id=str(gen_session.id),
            version_number=version_number,
            schema=result["schema"],
            validation=result["validation"],
            dxf_path=result.get("dxf_path")
        )


@router.post("/modify", response_model=GenerateResponse)
async def modify_drawing(req: ModifyRequest) -> GenerateResponse:
    """기존 도면 수정."""
    async with SessionLocal() as session:
        # 세션 조회
        gen_session = await session.get(GenerationSession, req.session_id)
        if not gen_session:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

        # 최신 버전 조회
        versions_result = await session.execute(
            select(GenerationVersion)
            .where(GenerationVersion.session_id == req.session_id)
            .order_by(GenerationVersion.version_number.desc())
        )
        latest_version = versions_result.scalars().first()

        if not latest_version:
            raise HTTPException(status_code=400, detail="수정할 도면이 없습니다.")

        # 도면 수정
        try:
            from apps.worker.src.pipelines.generate_dxf import run_ai_modification
            result = await run_ai_modification(
                prompt=req.prompt,
                current_schema=latest_version.schema_json,
            )
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("error", "수정 실패"))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("도면 수정 실패: %s", e)
            raise HTTPException(status_code=500, detail=f"도면 수정 실패: {str(e)}")

        # 새 버전 저장
        new_version_number = latest_version.version_number + 1
        gen_version = GenerationVersion(
            session_id=req.session_id,
            version_number=new_version_number,
            prompt=req.prompt,
            schema_json=result["schema"],
            validation_result=result["validation"],
            dxf_path=result.get("dxf_path")
        )
        session.add(gen_version)

        # 대화 히스토리 업데이트
        history = gen_session.conversation_history or []
        history.append({
            "role": "user",
            "content": req.prompt
        })
        history.append({
            "role": "assistant",
            "content": f"도면을 수정했습니다. (버전 {new_version_number})"
        })
        gen_session.conversation_history = history

        await session.commit()

        return GenerateResponse(
            session_id=req.session_id,
            version_number=new_version_number,
            schema=result["schema"],
            validation=result["validation"],
            dxf_path=result.get("dxf_path")
        )


@router.get("/sessions/{project_id}", response_model=list[SessionResponse])
async def list_sessions(project_id: str) -> list[SessionResponse]:
    """프로젝트의 생성 세션 목록 조회."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(GenerationSession)
            .where(GenerationSession.project_id == project_id)
            .order_by(GenerationSession.created_at.desc())
        )
        sessions = result.scalars().all()

        response = []
        for s in sessions:
            # 버전 수 계산
            version_result = await session.execute(
                select(GenerationVersion).where(
                    GenerationVersion.session_id == str(s.id)
                )
            )
            version_count = len(version_result.scalars().all())

            response.append(SessionResponse(
                id=str(s.id),
                project_id=str(s.project_id),
                title=s.title,
                status=s.status,
                version_count=version_count,
                created_at=s.created_at.isoformat()
            ))

        return response


@router.get("/session/{session_id}/versions")
async def get_session_versions(session_id: str) -> list[dict]:
    """세션의 모든 버전 조회."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(GenerationVersion)
            .where(GenerationVersion.session_id == session_id)
            .order_by(GenerationVersion.version_number.asc())
        )
        versions = result.scalars().all()

        return [
            {
                "version_number": v.version_number,
                "prompt": v.prompt,
                "schema": v.schema_json,
                "validation": v.validation_result,
                "dxf_path": v.dxf_path,
                "created_at": v.created_at.isoformat()
            }
            for v in versions
        ]


@router.get("/session/{session_id}/latest")
async def get_latest_version(session_id: str) -> dict:
    """세션의 최신 버전 조회."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(GenerationVersion)
            .where(GenerationVersion.session_id == session_id)
            .order_by(GenerationVersion.version_number.desc())
        )
        latest = result.scalars().first()

        if not latest:
            raise HTTPException(status_code=404, detail="버전을 찾을 수 없습니다.")

        return {
            "version_number": latest.version_number,
            "prompt": latest.prompt,
            "schema": latest.schema_json,
            "validation": latest.validation_result,
            "dxf_path": latest.dxf_path,
            "created_at": latest.created_at.isoformat()
        }
