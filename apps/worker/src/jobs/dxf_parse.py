"""DXF 파싱 및 Raw Entity 저장 잡."""
import logging
import os
from pathlib import Path
from typing import Optional, Any, Iterable

try:
    import ezdxf  # type: ignore
except ImportError:  # pragma: no cover - 라이브러리 미설치 시 런타임에 확인
    ezdxf = None

from geoalchemy2 import WKTElement
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from packages.db.src.session import SessionLocal
from packages.db.src import models

logger = logging.getLogger(__name__)

STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
EZDXF_CACHE_DIR = Path(os.getenv("EZDXF_CACHE_DIR", ".cache/ezdxf"))
UNIT_INPUT = os.getenv("UNIT_INPUT", "mm")
UNIT_OUTPUT = os.getenv("UNIT_OUTPUT", "m")


def _ensure_ezdxf():
    if ezdxf is None:
        raise RuntimeError("ezdxf가 설치되어 있지 않습니다. `pip install ezdxf` 후 재시도하세요.")
    os.environ.setdefault("EZDXF_CACHE_DIR", str(EZDXF_CACHE_DIR))
    EZDXF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _mm_to_m(value: float | None) -> float | None:
    if value is None:
        return None
    if UNIT_INPUT == "mm" and UNIT_OUTPUT == "m":
        return value / 1000.0
    return value


def _area_mm2_to_m2(value: float | None) -> float | None:
    if value is None:
        return None
    if UNIT_INPUT == "mm" and UNIT_OUTPUT == "m":
        return value / 1_000_000.0
    return value


def _bbox_to_wkt(bbox) -> str | None:
    if bbox is None:
        return None
    (minx, miny, _), (maxx, maxy, _) = bbox.extmin, bbox.extmax
    return f"POLYGON(({minx} {miny}, {maxx} {miny}, {maxx} {maxy}, {minx} {maxy}, {minx} {miny}))"


def _geom_wkt(entity) -> str | None:
    dtype = entity.dxftype()
    try:
        if dtype == "LINE":
            s = entity.dxf.start
            e = entity.dxf.end
            return f"LINESTRING({s[0]} {s[1]}, {e[0]} {e[1]})"
        if dtype in ("LWPOLYLINE", "POLYLINE"):
            pts = list(entity.get_points("xy"))
            if not pts:
                return None
            coord_str = ", ".join(f"{x} {y}" for x, y in pts)
            return f"LINESTRING({coord_str})"
        if dtype == "CIRCLE":
            c = entity.dxf.center
            return f"POINT({c[0]} {c[1]})"
        if dtype == "ARC":
            start = entity.start_point
            end = entity.end_point
            return f"LINESTRING({start[0]} {start[1]}, {end[0]} {end[1]})"
        if dtype in ("TEXT", "MTEXT", "HATCH", "INSERT", "BLOCK"):
            # 위치가 있으면 포인트로 기록
            if hasattr(entity.dxf, "insert"):
                ins = entity.dxf.insert
                return f"POINT({ins[0]} {ins[1]})"
    except Exception:
        return None
    return None


def extract_counts(doc) -> dict:
    msp = doc.modelspace()
    entity_types = ["LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT", "HATCH", "INSERT"]
    counts = {etype: len(msp.query(etype)) for etype in entity_types}
    counts["layers"] = len(doc.layers)
    return counts


def _entity_length(entity) -> float | None:
    try:
        return float(entity.length())
    except Exception:
        return None


def _entity_area(entity) -> float | None:
    try:
        if entity.dxftype() == "HATCH":
            return float(entity.get_area())
    except Exception:
        return None
    return None


def _properties(entity) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if entity.dxftype() in ("TEXT", "MTEXT"):
        props["text"] = entity.plain_text() if hasattr(entity, "plain_text") else entity.dxf.text
    if entity.dxftype() in ("INSERT", "BLOCK"):
        props["insert"] = {
            "location": getattr(entity.dxf, "insert", None) and list(entity.dxf.insert),
            "scale": getattr(entity.dxf, "scale", None) and list(entity.dxf.scale),
            "rotation": getattr(entity.dxf, "rotation", None),
            "name": getattr(entity.dxf, "name", None),
        }
    return props


async def run(file_id: Optional[str] = None, src: Optional[Path] = None) -> None:
    """단일 DXF 파일을 파싱하고 dxf_entities_raw 및 스탯을 DB에 저장.

    file_id가 없으면 DB 저장을 건너뛰고 로그만 남긴다.
    """
    _ensure_ezdxf()
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)

    if src is None:
        candidates = sorted(STORAGE_DERIVED_PATH.glob("*.dxf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            logger.info("파싱할 DXF가 없습니다 (경로: %s)", STORAGE_DERIVED_PATH)
            return
        src = candidates[0]

    logger.info("DXF 파싱 시작: %s", src)
    doc = ezdxf.readfile(src)
    counts = extract_counts(doc)
    logger.info("DXF 카운트: %s", counts)

    if file_id is None:
        logger.warning("file_id가 없어 DB 저장을 건너뜁니다. (파일: %s)", src)
        return

    msp = doc.modelspace()
    entities = []
    for entity in msp:
        dtype = entity.dxftype()
        if dtype not in ("LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT", "HATCH", "INSERT", "BLOCK"):
            continue

        bbox = entity.bbox() if hasattr(entity, "bbox") else None
        bbox_wkt = _bbox_to_wkt(bbox)
        geom_wkt = _geom_wkt(entity)
        length = _entity_length(entity)
        area = _entity_area(entity)

        rec = models.DxfEntityRaw(
            file_id=file_id,
            type=dtype,
            layer=entity.dxf.layer if hasattr(entity, "dxf") else None,
            geom=WKTElement(geom_wkt, srid=models.SRID_LOCAL_CAD) if geom_wkt else None,
            bbox=WKTElement(bbox_wkt, srid=models.SRID_LOCAL_CAD) if bbox_wkt else None,
            length=_mm_to_m(length),
            area=_area_mm2_to_m2(area),
            properties=_properties(entity),
        )
        entities.append(rec)

    async with SessionLocal() as session:
        try:
            # entity bulk insert
            session.add_all(entities)
            # files stats 업데이트
            await session.execute(
                text(
                    """
                    update files set
                        layer_count = :layers,
                        entity_count = :entities
                    where id = :file_id
                    """
                ),
                {
                    "layers": counts.get("layers"),
                    "entities": sum(v for k, v in counts.items() if k != "layers"),
                    "file_id": file_id,
                },
            )
            # conversion_logs 성공 기록
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at, layer_count, entity_count)
                    values (:file_id, 'success', now(), now(), :layers, :entities)
                    """
                ),
                {
                    "file_id": file_id,
                    "layers": counts.get("layers"),
                    "entities": sum(v for k, v in counts.items() if k != "layers"),
                },
            )
            await session.commit()
            logger.info("DXF 파싱 완료 및 DB 저장: %s (entities=%s)", file_id, len(entities))
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("DB 저장 중 오류: %s", e)
            raise
