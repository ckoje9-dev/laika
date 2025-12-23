"""업로드 초기화 및 변환 상태 조회 라우터."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.src.session import get_session
from packages.db.src import models as db_models

router = APIRouter(tags=["uploads"])

STORAGE_ORIGINAL_PATH = Path(os.getenv("STORAGE_ORIGINAL_PATH", "storage/original"))


class UploadInitRequest(BaseModel):
    version_id: str
    filename: str


class UploadInitResponse(BaseModel):
    file_id: str
    upload_path: str
    storage_path: str
    type: str


def _infer_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext in ("dwg",):
        return "dwg"
    if ext in ("dxf",):
        return "dxf"
    if ext in ("pdf",):
        return "pdf"
    if ext in ("png", "jpg", "jpeg", "webp"):
        return "img"
    return "doc"


@router.post("/init", response_model=UploadInitResponse, status_code=201)
async def init_upload(payload: UploadInitRequest, session: AsyncSession = Depends(get_session)):
    # 버전 존재 확인
    exists = await session.execute(select(db_models.Version.id).where(db_models.Version.id == payload.version_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="version not found")

    ftype = _infer_type(payload.filename)
    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    storage_path = STORAGE_ORIGINAL_PATH / payload.filename

    file_row = db_models.File(
        version_id=payload.version_id,
        type=ftype,
        path_original=str(storage_path),
        read_only=(ftype == "dwg"),
    )
    session.add(file_row)
    await session.commit()
    await session.refresh(file_row)

    # 업로드는 로컬 경로로 가정 (서명 URL이 없다면 파일 시스템 직접 업로드)
    upload_path = str(storage_path)
    return UploadInitResponse(file_id=str(file_row.id), upload_path=upload_path, storage_path=str(storage_path), type=ftype)


@router.get("/{file_id}/status")
async def get_upload_status(file_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(db_models.ConversionLog).where(db_models.ConversionLog.file_id == file_id).order_by(db_models.ConversionLog.id.desc()))
    log = result.scalars().first()
    status = log.status if log else "pending"
    return {"file_id": file_id, "status": status, "message": log.message if log else None}
