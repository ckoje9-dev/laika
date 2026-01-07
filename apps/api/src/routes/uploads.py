"""업로드 초기화 및 변환/파싱 상태 조회 라우터."""
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import tempfile
import zipfile
import tempfile
import zipfile

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


class BulkDownloadRequest(BaseModel):
    file_ids: list[str]
    kind: str = "dxf"


class BulkDownloadRequest(BaseModel):
    file_ids: list[str]
    kind: str = "dxf"


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


def _parse1_json_path(file_row: db_models.File) -> Path | None:
    target = file_row.path_dxf or file_row.path_original
    if not target:
        return None
    stem = Path(target).stem
    return STORAGE_DERIVED_PATH / f"{stem}_parse1.json"


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


def _extract_layers_blocks_from_parse1(data: Any) -> tuple[list[str], list[str]]:
    """parse1(원본 dxf-parser 결과)에서 레이어/블록 이름 추출."""
    if not isinstance(data, dict):
        return [], []
    sections = data.get("sections", {}) if isinstance(data.get("sections", {}), dict) else {}
    tables = sections.get("tables") or data.get("tables") or {}
    blocks_section = sections.get("blocks") or data.get("blocks") or {}
    layers = []
    blocks = []
    try:
        raw_layers = None
        if isinstance(tables, dict):
            raw_layers = (
                tables.get("layer", {}).get("layers")
                or tables.get("layers")
                or tables.get("LAYER", {}).get("layers")
                or tables.get("layer")
            )
        if isinstance(raw_layers, dict):
            raw_layers = raw_layers.get("layers") or list(raw_layers.values())
        if isinstance(raw_layers, list):
            for l in raw_layers:
                if isinstance(l, dict):
                    name = l.get("name") or l.get("layer")
                else:
                    name = l
                if name:
                    layers.append(str(name))
    except Exception:
        layers = []
    try:
        raw_blocks = blocks_section
        if isinstance(raw_blocks, dict):
            # dxf-parser blocks는 {name: {...}} 형태일 수도 있음
            raw_blocks = list(raw_blocks.values())
        if isinstance(raw_blocks, list):
            for b in raw_blocks:
                name = None
                if isinstance(b, dict):
                    name = b.get("name") or b.get("block") or b.get("id")
                else:
                    name = b
                if name:
                    blocks.append(str(name))
    except Exception:
        blocks = []
    return layers, blocks


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
        enqueue("apps.worker.src.pipelines.convert.dwg_to_dxf.run", str(storage_path), str(file_row.id))
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
    table_path = None
    tables = None
    layers: list[dict] = []
    blocks: list[dict] = []
    parse1_data = _load_json(_parse1_json_path(file_row))
    sections_row = await session.get(db_models.DxfParseSection, file_id)
    if metadata:
        tables_entry = next((m for m in metadata if isinstance(m, dict) and m.get("section") == "tables"), {})
        layers = tables_entry.get("layers") or []
        blocks = tables_entry.get("block_records") or []
    elif parse1_data:
        parse1_layers, parse1_blocks = _extract_layers_blocks_from_parse1(parse1_data)
        layers = [{"name": n} for n in parse1_layers]
        blocks = [{"name": n} for n in parse1_blocks]

    # 섹션 테이블 기반 레이어/블록(1차 파싱 기준)
    if sections_row:
        try:
            if not layers and sections_row.tables:
                raw_layers = (
                    sections_row.tables.get("layer", {}).get("layers")
                    or sections_row.tables.get("layers")
                    or sections_row.tables.get("layer")
                )
                if isinstance(raw_layers, dict):
                    raw_layers = raw_layers.get("layers") or list(raw_layers.values())
                if isinstance(raw_layers, list):
                    layers = [{"name": (l.get("name") if isinstance(l, dict) else l)} for l in raw_layers if (l.get("name") if isinstance(l, dict) else l)]
            if not blocks and sections_row.blocks:
                raw_blocks = sections_row.blocks
                if isinstance(raw_blocks, dict):
                    raw_blocks = list(raw_blocks.values())
                if isinstance(raw_blocks, list):
                    blocks = [
                        {"name": (b.get("name") if isinstance(b, dict) else b)}
                        for b in raw_blocks
                        if (b.get("name") if isinstance(b, dict) else b)
                    ]
        except Exception:
            pass

    use_sections_entities = bool(sections_row and isinstance(sections_row.entities, list))
    if use_sections_entities:
        src_entities = sections_row.entities
        total = len(src_entities)
        counts: dict[str, int] = {}
        for ent in src_entities:
            if isinstance(ent, dict):
                dtype = ent.get("type")
                if dtype:
                    counts[str(dtype)] = counts.get(str(dtype), 0) + 1
        slice_start = offset or 0
        slice_end = slice_start + limit if limit is not None else None
        sliced = src_entities[slice_start:slice_end]
        entities = []
        for idx, ent in enumerate(sliced, start=slice_start + 1):
            if not isinstance(ent, dict):
                continue
            entities.append(
                {
                    "id": idx,
                    "type": ent.get("type"),
                    "layer": ent.get("layer") or ent.get("layerName"),
                    "length": None,
                    "area": None,
                    "properties": ent,
                }
            )
    else:
        counts = {}
        total = 0
        entities = []

    # dxf_entities_raw를 더 이상 사용하지 않음

    return {
        "file_id": file_id,
        "metadata": metadata,
        "counts": counts,
        "total": total,
        "entities": entities,
        "meta_path": str(meta_path) if meta_path else None,
        "layers": layers,
        "blocks": blocks,
        "tables": tables,
        "tables_path": str(table_path) if table_path else None,
    }


@router.post("/{file_id}/parse", response_model=ParseResponse)
async def enqueue_parse(file_id: str, session: AsyncSession = Depends(get_session)):
    # file 존재 확인
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    # DXF 업로드인데 path_dxf가 비어있는 경우 path_original을 그대로 사용하도록 보정
    if not file_row.path_dxf and file_row.type == "dxf" and file_row.path_original:
        file_row.path_dxf = file_row.path_original
        await session.commit()

    # DWG인 경우 변환이 안된 상태라면 변환+파싱 파이프라인을 큐에 넣는다.
    if not file_row.path_dxf and file_row.type == "dwg":
        enqueued = False
        message: str | None = None
        try:
            enqueue("apps.worker.src.pipelines.convert.convert_and_parse.run", file_id=file_id)
            enqueued = True
            message = "DWG 변환 후 파싱을 위한 파이프라인을 실행했습니다."
        except Exception as e:  # pragma: no cover - 큐 설정 오류 시 로그를 남기고 반환
            import logging

            logging.getLogger(__name__).warning("convert_and_parse enqueue 실패: %s", e)
            message = str(e)

        return ParseResponse(file_id=file_id, enqueued=enqueued, message=message, parsed=None)

    if not file_row.path_dxf:
        raise HTTPException(status_code=400, detail="DXF가 아직 생성되지 않았습니다. 변환 완료 후 파싱하세요.")

    enqueued = False
    message: str | None = None
    try:
        enqueue("apps.worker.src.pipelines.parse.parse1_node.run", file_id=file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover - 큐 설정 오류 시 로그를 남기고 반환
        import logging

        logging.getLogger(__name__).warning("parse1 enqueue 실패: %s", e)
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
        enqueue("apps.worker.src.pipelines.convert.dwg_to_dxf.run", file_row.path_original, file_id)
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
        enqueue("apps.worker.src.pipelines.parse.dxf_parse2", file_id=file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("dxf_parse2 enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message, parsed=False)


@router.post("/bulk-download")
async def bulk_download(
    payload: BulkDownloadRequest, session: AsyncSession = Depends(get_session)
):
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="file_ids is required")

    paths: list[Path] = []
    names: list[str] = []
    for fid in payload.file_ids:
        file_row = await session.get(db_models.File, fid)
        if not file_row:
            continue
        if payload.kind == "dxf":
            if file_row.path_dxf and Path(file_row.path_dxf).exists():
                paths.append(Path(file_row.path_dxf))
                names.append(Path(file_row.path_dxf).name)
        elif payload.kind == "original":
            if file_row.path_original and Path(file_row.path_original).exists():
                paths.append(Path(file_row.path_original))
                names.append(Path(file_row.path_original).name)
    if not paths:
        raise HTTPException(status_code=404, detail="no files ready")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p, name in zip(paths, names):
            zf.write(p, arcname=name)
    return FileResponse(tmp.name, media_type="application/zip", filename="dxf_bundle.zip")
