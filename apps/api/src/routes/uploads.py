"""업로드 초기화 및 변환/파싱 상태 조회 라우터."""
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import tempfile
import zipfile

from packages.db.src.session import get_session
from packages.db.src import models as db_models
from packages.queue import enqueue

convert_router = APIRouter(tags=["convert"])
parsing_router = APIRouter(tags=["parsing"])

STORAGE_ORIGINAL_PATH = Path(os.getenv("STORAGE_ORIGINAL_PATH", "storage/original"))
STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
DEFAULT_PROJECT_NAME = os.getenv("DEFAULT_PROJECT_NAME", "default")


async def _ensure_default_project(session: AsyncSession) -> db_models.Project:
    result = await session.execute(select(db_models.Project).where(db_models.Project.name == DEFAULT_PROJECT_NAME))
    project = result.scalar_one_or_none()
    if project:
        return project
    project = db_models.Project(name=DEFAULT_PROJECT_NAME)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def _ensure_default_version(session: AsyncSession, label: str) -> db_models.Version:
    project = await _ensure_default_project(session)
    result = await session.execute(
        select(db_models.Version).where(
            db_models.Version.project_id == project.id,
            db_models.Version.label == label,
        )
    )
    version = result.scalar_one_or_none()
    if version:
        return version
    version = db_models.Version(project_id=project.id, label=label)
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


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


class Parse2Request(BaseModel):
    selections: dict[str, list[str]] | None = None
    rules: list[dict[str, Any]] | None = None


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


def _entities_csv_path(file_row: db_models.File) -> Path | None:
    target = file_row.path_dxf or file_row.path_original
    if not target:
        return None
    stem = Path(target).stem
    return STORAGE_DERIVED_PATH / f"{stem}_entities.csv"


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


def _load_entities_csv(path: Path | None) -> tuple[list[dict], list[str]]:
    if path is None or not path.exists():
        return [], []
    try:
        with path.open("r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            rows = [row for row in reader]
            columns = reader.fieldnames or []
            return rows, columns
    except OSError:
        return [], []


def _ensure_entities_csv(file_row: db_models.File) -> Path | None:
    parse1_path = _parse1_json_path(file_row)
    if not parse1_path or not parse1_path.exists():
        return None
    csv_path = _entities_csv_path(file_row)
    if csv_path is None:
        return None
    if csv_path.exists():
        return csv_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    base_dir = Path(__file__).resolve().parents[3]
    script_path = base_dir / "worker" / "src" / "pipelines" / "parse" / "extract_entities_table.py"
    try:
        subprocess.run(
            [sys.executable, str(script_path), str(parse1_path), str(csv_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or exc.stdout or "entities table 생성 실패"
        raise HTTPException(status_code=500, detail=detail) from exc
    return csv_path


async def _save_upload(
    session: AsyncSession, file: UploadFile, *, version_label: str, allowed_exts: tuple[str, ...]
) -> UploadInitResponse:
    ftype = _infer_type(file.filename)
    if ftype not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"{', '.join(allowed_exts)}만 업로드할 수 있습니다.")

    version = await _ensure_default_version(session, version_label)
    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    storage_path = STORAGE_ORIGINAL_PATH / file.filename

    with storage_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    file_row = db_models.File(
        version_id=version.id,
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


@convert_router.post("/upload", response_model=UploadInitResponse, status_code=201)
async def upload_convert(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    return await _save_upload(session, file, version_label="convert", allowed_exts=("dwg", "dxf"))


@parsing_router.post("/upload", response_model=UploadInitResponse, status_code=201)
async def upload_parsing(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    return await _save_upload(session, file, version_label="parse", allowed_exts=("dxf",))


@convert_router.get("/{file_id}/status")
async def get_convert_status(file_id: str, session: AsyncSession = Depends(get_session)):
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


@parsing_router.get("/{file_id}/status")
async def get_parsing_status(file_id: str, session: AsyncSession = Depends(get_session)):
    return await get_convert_status(file_id, session)




@convert_router.get("/{file_id}/download")
async def download_convert_file(file_id: str, kind: str = "dxf", session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    if kind in ("dxf", "dwg"):
        if not file_row.path_dxf or not Path(file_row.path_dxf).exists():
            raise HTTPException(status_code=404, detail="converted file not ready")
        media_type = "application/dxf" if kind == "dxf" else "application/octet-stream"
        return FileResponse(file_row.path_dxf, media_type=media_type, filename=Path(file_row.path_dxf).name)

    if kind == "original":
        if not file_row.path_original or not Path(file_row.path_original).exists():
            raise HTTPException(status_code=404, detail="original file not found")
        return FileResponse(file_row.path_original, media_type="application/octet-stream", filename=Path(file_row.path_original).name)

    raise HTTPException(status_code=400, detail="unsupported kind")


@parsing_router.get("/{file_id}/download")
async def download_parsing_file(file_id: str, kind: str = "dxf", session: AsyncSession = Depends(get_session)):
    return await download_convert_file(file_id, kind, session)


@parsing_router.get("/{file_id}/parse1-download")
async def download_parse1(file_id: str, session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")
    parse1_path = _parse1_json_path(file_row)
    if not parse1_path or not parse1_path.exists():
        raise HTTPException(status_code=404, detail="parse1 not ready")
    return FileResponse(parse1_path, media_type="application/json", filename=parse1_path.name)


@parsing_router.get("/{file_id}/parsed1")
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
    sections_row = await session.get(db_models.DxfParseSection, file_id)

    # dxf_parse_sections: sections.tables.layer.layers / sections.blocks 의 key만 사용
    if sections_row:
        tables = sections_row.tables if isinstance(sections_row.tables, dict) else {}
        layer_dict = tables.get("layer", {}).get("layers") if isinstance(tables.get("layer"), dict) else None
        layers = [{"name": k} for k in layer_dict.keys() if k] if isinstance(layer_dict, dict) else []
        block_dict = sections_row.blocks if isinstance(sections_row.blocks, dict) else {}
        blocks = [{"name": k} for k in block_dict.keys() if k]

    # dxf_parse_sections를 유일한 소스로 사용

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


@parsing_router.get("/{file_id}/entities-table")
async def get_entities_table(file_id: str, session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    # 1차: 파일 시스템의 CSV 시도
    try:
        csv_path = _ensure_entities_csv(file_row)
        if csv_path and csv_path.exists():
            rows, columns = _load_entities_csv(csv_path)
            return {
                "file_id": file_id,
                "rows": rows,
                "columns": columns,
                "csv_path": str(csv_path),
            }
    except Exception:
        pass  # 파일 기반 실패 시 DB fallback

    # 2차: DB의 dxf_parse_sections.entities에서 직접 생성
    sections_row = await session.get(db_models.DxfParseSection, file_id)
    if not sections_row:
        raise HTTPException(status_code=404, detail="entities table not ready")

    entities = sections_row.entities if isinstance(sections_row.entities, list) else []
    if not entities:
        return {"file_id": file_id, "rows": [], "columns": [], "csv_path": None}

    all_keys: set[str] = set()
    for ent in entities:
        if isinstance(ent, dict):
            all_keys.update(ent.keys())
    columns = ["handle"] + sorted(k for k in all_keys if k != "handle")
    rows = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        row = {}
        for key in columns:
            value = ent.get(key)
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                row[key] = value
        rows.append(row)
    return {
        "file_id": file_id,
        "rows": rows,
        "columns": columns,
        "csv_path": None,
    }


@parsing_router.get("/{file_id}/semantic-summary")
async def get_semantic_summary(file_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(db_models.SemanticObject).where(db_models.SemanticObject.file_id == file_id))
    rows = result.scalars().all()
    borders = []
    axis_summaries = []
    columns = []
    def _decode_props(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}
    for row in rows:
        props = _decode_props(row.properties)
        if row.kind == "border":
            if not props.get("bbox_world"):
                continue
            borders.append(
                {
                    "handle": props.get("insert_handle"),
                    "block_name": props.get("block_name"),
                    "bbox_world": props.get("bbox_world"),
                }
            )
        elif row.kind == "axis_summary":
            axis_summaries.append(props)
        elif row.kind == "concrete_column":
            columns.append(props)

    column_types = {}
    column_type_counts = {}
    for col in columns:
        ctype = col.get("column_type")
        size = col.get("size")
        if not ctype or not size:
            continue
        column_types.setdefault(ctype, size)
        column_type_counts[ctype] = column_type_counts.get(ctype, 0) + 1
    return {
        "file_id": file_id,
        "border_count": len(borders),
        "borders": borders,
        "axis_summaries": axis_summaries,
        "column_count": len(columns),
        "column_types": [
            {"type": k, "size": v, "count": column_type_counts.get(k, 0)}
            for k, v in sorted(column_types.items(), key=lambda x: x[0])
        ],
    }


@parsing_router.post("/{file_id}/parse1", response_model=ParseResponse)
async def enqueue_parse1(file_id: str, session: AsyncSession = Depends(get_session)):
    # file 존재 확인
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    # DXF만 처리하므로 path_dxf가 비어있으면 path_original을 사용
    if not file_row.path_dxf and file_row.path_original:
        file_row.path_dxf = file_row.path_original
        await session.commit()

    if not file_row.path_dxf:
        raise HTTPException(status_code=400, detail="DXF 경로가 없습니다. 파일 업로드를 확인하세요.")

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


@convert_router.post("/{file_id}/convert", response_model=ParseResponse)
async def enqueue_convert(file_id: str, session: AsyncSession = Depends(get_session)):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")
    if not file_row.path_original:
        raise HTTPException(status_code=400, detail="path_original is missing")

    enqueued = False
    message: str | None = None
    job_path = None
    if file_row.type == "dwg":
        job_path = "apps.worker.src.pipelines.convert.dwg_to_dxf.run"
    elif file_row.type == "dxf":
        job_path = "apps.worker.src.pipelines.convert.dxf_to_dwg.run"
    else:
        raise HTTPException(status_code=400, detail="unsupported file type for convert")

    try:
        enqueue(job_path, file_row.path_original, file_id)
        enqueued = True
    except Exception as e:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("convert enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message)


@parsing_router.post("/{file_id}/parse2", response_model=ParseResponse)
async def enqueue_parse2(
    file_id: str,
    payload: Parse2Request | None = None,
    session: AsyncSession = Depends(get_session),
):
    file_row = await session.get(db_models.File, file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="file not found")

    enqueued = False
    message: str | None = None
    selections = payload.selections if payload else None
    rules = payload.rules if payload else None
    try:
        enqueue("apps.worker.src.pipelines.parse.dxf_parse2", file_id=file_id, selections=selections, rules=rules)
        enqueued = True
    except Exception as e:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("dxf_parse2 enqueue 실패: %s", e)
        message = str(e)

    return ParseResponse(file_id=file_id, enqueued=enqueued, message=message, parsed=False)


@convert_router.post("/bulk-download")
async def bulk_download(payload: BulkDownloadRequest, session: AsyncSession = Depends(get_session)):
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="file_ids is required")

    paths: list[Path] = []
    names: list[str] = []
    for fid in payload.file_ids:
        file_row = await session.get(db_models.File, fid)
        if not file_row:
            continue
        if payload.kind in ("dxf", "dwg"):
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
