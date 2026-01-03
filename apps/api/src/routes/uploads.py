"""업로드 초기화 및 변환/파싱 상태 조회 라우터."""
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.src.session import get_session
from packages.db.src import models as db_models
from packages.queue import enqueue

router = APIRouter(tags=["uploads"])

STORAGE_ORIGINAL_PATH = Path(os.getenv("STORAGE_ORIGINAL_PATH", "storage/original"))
STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))


class UploadInitRequest(BaseModel):
    version_id: str
    filename: str


class UploadInitResponse(BaseModel):
    file_id: str
    upload_path: str
    storage_path: str
    type: str
    enqueued: bool


class ParseResponse(BaseModel):
    file_id: str
    enqueued: bool
    message: str | None = None
    parsed: bool | None = None
    meta_path: str | None = None


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


def _meta_jsonl_path(file_row: db_models.File) -> Path | None:
    if not file_row.path_dxf:
        return None
    stem = Path(file_row.path_dxf).stem
    return STORAGE_DERIVED_PATH / f"{stem}_meta.jsonl"


def _tables_json_path(file_row: db_models.File) -> Path | None:
    if not file_row.path_dxf:
        return None
    stem = Path(file_row.path_dxf).stem
    return STORAGE_DERIVED_PATH / f"{stem}_tables.json"


def _load_jsonl(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    records = []
    try:
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records


def _load_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return None


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
    # 변환 잡 enqueue (동기 루틴이므로 실패해도 요청 자체는 201 반환)
    enqueued = False
    try:
        enqueue("apps.worker.src.jobs.dwg_to_dxf.run", str(storage_path), str(file_row.id))
        enqueued = True
    except Exception as e:
        # 큐 장애는 로깅만 하고 반환
        import logging

        logging.getLogger(__name__).warning("enqueue 실패: %s", e)

    return UploadInitResponse(
        file_id=str(file_row.id),
        upload_path=upload_path,
        storage_path=str(storage_path),
        type=ftype,
        enqueued=enqueued,
    )


@router.get("/{file_id}/status")
async def get_upload_status(file_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(db_models.ConversionLog).where(db_models.ConversionLog.file_id == file_id).order_by(db_models.ConversionLog.id.desc()))
    log = result.scalars().first()
    status = log.status if log else "pending"
    file_row = await session.get(db_models.File, file_id)
    return {
        "file_id": file_id,
        "status": status,
        "message": log.message if log else None,
        "path_dxf": file_row.path_dxf if file_row else None,
        "path_original": file_row.path_original if file_row else None,
    }


@router.post("/upload", response_model=UploadInitResponse, status_code=201)
async def upload_file(version_id: str = Form(...), file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    # 버전 존재 확인
    exists = await session.execute(select(db_models.Version.id).where(db_models.Version.id == version_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="version not found")

    ftype = _infer_type(file.filename)
    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    storage_path = STORAGE_ORIGINAL_PATH / file.filename

    # 파일 저장 (chunk 단위)
    with storage_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    file_row = db_models.File(
        version_id=version_id,
        type=ftype,
        path_original=str(storage_path),
        read_only=(ftype == "dwg"),
    )
    session.add(file_row)
    await session.commit()
    await session.refresh(file_row)

    return UploadInitResponse(
        file_id=str(file_row.id),
        upload_path=str(storage_path),
        storage_path=str(storage_path),
        type=ftype,
        enqueued=False,
    )


@router.get("/{file_id}/download")
async def download_file(file_id: str, kind: str = "dxf", session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    if kind == "dxf":
        if not file_row.path_dxf or not Path(file_row.path_dxf).exists():
            raise HTTPException(status_code=404, detail="DXF not ready")
        return FileResponse(file_row.path_dxf, media_type="application/dxf", filename=Path(file_row.path_dxf).name)

    if kind == "original":
        if not file_row.path_original or not Path(file_row.path_original).exists():
            raise HTTPException(status_code=404, detail="original file not found")
        return FileResponse(file_row.path_original, media_type="application/octet-stream", filename=Path(file_row.path_original).name)

    raise HTTPException(status_code=400, detail="unsupported kind")


@router.get("/{file_id}/parsed")
async def get_parsed_preview(
    file_id: str,
    limit: int | None = None,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    meta_path = _meta_jsonl_path(file_row)
    metadata = _load_jsonl(meta_path)
    table_path = _tables_json_path(file_row)
    tables = _load_json(table_path)

    counts_stmt = (
        select(db_models.DxfEntityRaw.type, func.count())
        .where(db_models.DxfEntityRaw.file_id == file_id)
        .group_by(db_models.DxfEntityRaw.type)
    )
    counts_result = await session.execute(counts_stmt)
    counts = {t: c for t, c in counts_result.all()}

    total_stmt = select(func.count()).where(db_models.DxfEntityRaw.file_id == file_id)
    total = (await session.execute(total_stmt)).scalar_one()

    entities_stmt = select(
        db_models.DxfEntityRaw.id,
        db_models.DxfEntityRaw.type,
        db_models.DxfEntityRaw.layer,
        db_models.DxfEntityRaw.length,
        db_models.DxfEntityRaw.area,
        db_models.DxfEntityRaw.properties,
    ).where(db_models.DxfEntityRaw.file_id == file_id).order_by(db_models.DxfEntityRaw.id).offset(offset)
    if limit is not None:
        entities_stmt = entities_stmt.limit(limit)
    entity_rows = await session.execute(entities_stmt)
    entities = []
    for rid, dtype, layer, length, area, props in entity_rows.all():
        entities.append(
            {
                "id": rid,
                "type": dtype,
                "layer": layer,
                "length": float(length) if length is not None else None,
                "area": float(area) if area is not None else None,
                "properties": props,
            }
        )

    return {
        "file_id": file_id,
        "metadata": metadata,
        "counts": counts,
        "total": total,
        "entities": entities,
        "meta_path": str(meta_path) if meta_path else None,
        "tables": tables,
        "tables_path": str(table_path) if table_path else None,
    }


@router.post("/{file_id}/parse", response_model=ParseResponse)
async def enqueue_parse(file_id: str, session: AsyncSession = Depends(get_session)):
    # file 존재 확인
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")
    if not file_row.path_dxf:
        raise HTTPException(status_code=400, detail="DXF가 아직 생성되지 않았습니다. 변환 완료 후 파싱하세요.")

    enqueued = False
    message: str | None = None
    try:
        enqueue("apps.worker.src.jobs.dxf_parse.run", file_id=file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover - 큐 설정 오류 시 로그를 남기고 반환
        import logging

        logging.getLogger(__name__).warning("dxf_parse enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message)


@router.post("/{file_id}/convert", response_model=ParseResponse)
async def enqueue_convert(file_id: str, session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")
    if not file_row.path_original:
        raise HTTPException(status_code=400, detail="path_original is missing")

    enqueued = False
    message: str | None = None
    try:
        enqueue("apps.worker.src.jobs.dwg_to_dxf.run", file_row.path_original, file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("dwg_to_dxf enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message)


@router.post("/{file_id}/parse2", response_model=ParseResponse)
async def enqueue_parse2(file_id: str, session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    enqueued = False
    message: str | None = None
    try:
        enqueue("apps.worker.src.jobs.dxf_parse2.run", file_id=file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("dxf_parse2 enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message)
