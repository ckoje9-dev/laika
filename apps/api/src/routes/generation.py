"""AI 도면 생성 엔드포인트."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from packages.db.src.session import SessionLocal
from packages.db.src.models import GenerationSession, GenerationVersion, Project, File, Version, DxfParseSection
from packages.generation.src import DrawingSchema

logger = logging.getLogger(__name__)
router = APIRouter(tags=["generation"])


async def _resolve_project_id(session, project_id_or_name: str) -> str:
    """프로젝트 ID 또는 이름으로 프로젝트를 찾고, 없으면 생성한다."""
    # UUID로 직접 조회
    project = await session.get(Project, project_id_or_name)
    if project:
        return str(project.id)

    # 이름으로 조회
    result = await session.execute(
        select(Project).where(Project.name == project_id_or_name)
    )
    project = result.scalar_one_or_none()
    if project:
        return str(project.id)

    # 없으면 생성
    project = Project(name=project_id_or_name)
    session.add(project)
    await session.flush()
    return str(project.id)


class GenerateRequest(BaseModel):
    """도면 생성 요청."""
    project_id: str
    prompt: str
    session_id: Optional[str] = None
    reference_file_ids: Optional[list[str]] = None


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
        # 프로젝트 조회 또는 생성
        project_id = await _resolve_project_id(session, req.project_id)

        # 세션 생성 또는 조회
        if req.session_id:
            gen_session = await session.get(GenerationSession, req.session_id)
            if not gen_session:
                raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        else:
            gen_session = GenerationSession(
                project_id=project_id,
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
                reference_file_ids=req.reference_file_ids,
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


@router.get("/reference-files/{project_id}")
async def list_reference_files(project_id: str) -> list[dict]:
    """프로젝트에서 참조 가능한 파싱된 파일 목록 조회."""
    async with SessionLocal() as session:
        # 프로젝트 ID 해석
        resolved_id = await _resolve_project_id(session, project_id)

        # 프로젝트의 모든 파일 조회 (파싱 데이터가 있는 것만)
        result = await session.execute(
            select(File, Version)
            .join(Version, File.version_id == Version.id)
            .where(Version.project_id == resolved_id)
            .order_by(File.created_at.desc())
        )
        rows = result.all()

        files = []
        for file, version in rows:
            # dxf_parse_sections 존재 여부 확인
            parse_section = await session.get(DxfParseSection, str(file.id))
            has_parsed = parse_section is not None

            files.append({
                "file_id": str(file.id),
                "type": file.type,
                "version_label": version.label or "default",
                "layer_count": file.layer_count or 0,
                "entity_count": file.entity_count or 0,
                "has_parsed": has_parsed,
                "created_at": file.created_at.isoformat(),
            })

        return files


@router.get("/download-dxf")
async def download_dxf(path: str):
    """생성된 DXF 파일 다운로드."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(
        file_path,
        media_type="application/dxf",
        filename=file_path.name,
    )


class ConvertToDwgRequest(BaseModel):
    dxf_path: str


@router.post("/convert-to-dwg")
async def convert_to_dwg(req: ConvertToDwgRequest):
    """DXF를 DWG로 변환."""
    import subprocess
    import os

    dxf_path = Path(req.dxf_path)
    if not dxf_path.exists():
        raise HTTPException(status_code=404, detail="DXF 파일을 찾을 수 없습니다.")

    dwg_path = dxf_path.with_suffix(".dwg")

    # ODA File Converter 사용
    oda_path = os.getenv("ODA_CONVERTER_PATH", "/usr/bin/ODAFileConverter")
    if not Path(oda_path).exists():
        raise HTTPException(status_code=500, detail="ODA File Converter가 설치되어 있지 않습니다.")

    input_dir = str(dxf_path.parent)
    output_dir = str(dwg_path.parent)

    try:
        subprocess.run(
            [oda_path, input_dir, output_dir, "ACAD2018", "DWG", "0", "1", dxf_path.name],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or exc.stdout or "DWG 변환 실패"
        raise HTTPException(status_code=500, detail=detail)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="DWG 변환 시간 초과")

    if not dwg_path.exists():
        raise HTTPException(status_code=500, detail="DWG 파일 생성 실패")

    return {"dwg_path": str(dwg_path)}


@router.get("/download-dwg")
async def download_dwg(path: str):
    """DWG 파일 다운로드."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=file_path.name,
    )
