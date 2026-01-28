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
from packages.db.src.models import Project, File, Version, DxfParseSection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["generation"])


async def _resolve_project_id(session, project_id_or_name: str) -> str:
    """프로젝트 ID 또는 이름으로 프로젝트를 찾고, 없으면 생성한다."""
    try:
        UUID(project_id_or_name)
        project = await session.get(Project, project_id_or_name)
        if project:
            return str(project.id)
    except (ValueError, AttributeError):
        pass

    result = await session.execute(
        select(Project).where(Project.name == project_id_or_name)
    )
    project = result.scalar_one_or_none()
    if project:
        return str(project.id)

    project = Project(name=project_id_or_name)
    session.add(project)
    await session.flush()
    return str(project.id)


class GenerateRequest(BaseModel):
    """도면 생성 요청."""
    project_id: str
    prompt: str
    template_file_id: Optional[str] = None
    conversation_history: Optional[list[dict]] = None


class GenerateResponse(BaseModel):
    """도면 생성 응답."""
    schema: Optional[dict] = None
    validation: Optional[dict] = None
    dxf_path: Optional[str] = None
    message: Optional[str] = None


@router.post("/generate", response_model=GenerateResponse)
async def generate_drawing(req: GenerateRequest) -> GenerateResponse:
    """도면 생성. 템플릿이 있으면 파싱 데이터 기반, 없으면 순수 LLM."""
    template_data = None

    # 템플릿 파일이 선택된 경우 파싱 데이터 조회
    if req.template_file_id:
        async with SessionLocal() as session:
            parse_section = await session.get(DxfParseSection, req.template_file_id)
            if parse_section:
                template_data = {
                    "file_id": req.template_file_id,
                    "layers": parse_section.tables.get("layers", {}) if parse_section.tables else {},
                    "blocks": parse_section.blocks or {},
                    "entities_sample": (parse_section.entities or [])[:100],  # 샘플만
                    "header": parse_section.header or {},
                }

    # 도면 생성
    try:
        from apps.worker.src.pipelines.generate_dxf import run_ai_generation
        result = await run_ai_generation(
            prompt=req.prompt,
            project_id=req.project_id,
            template_data=template_data,
            conversation_history=req.conversation_history or [],
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "생성 실패"))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("도면 생성 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"도면 생성 실패: {str(e)}")

    return GenerateResponse(
        schema=result.get("schema"),
        validation=result.get("validation"),
        dxf_path=result.get("dxf_path"),
        message=result.get("message", "도면을 생성했습니다."),
    )


@router.get("/reference-files/{project_id}")
async def list_reference_files(project_id: str) -> list[dict]:
    """프로젝트에서 참조 가능한 파싱된 파일 목록 조회."""
    async with SessionLocal() as session:
        resolved_id = await _resolve_project_id(session, project_id)

        result = await session.execute(
            select(File, Version)
            .join(Version, File.version_id == Version.id)
            .where(Version.project_id == resolved_id)
            .order_by(File.created_at.desc())
        )
        rows = result.all()

        files = []
        for file, version in rows:
            parse_section = await session.get(DxfParseSection, str(file.id))
            has_parsed = parse_section is not None

            raw_path = file.path_dxf or file.path_original or ""
            filename = Path(raw_path).name if raw_path else f"file-{str(file.id)[:8]}"

            files.append({
                "file_id": str(file.id),
                "filename": filename,
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
