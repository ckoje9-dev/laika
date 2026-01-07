"""DXF 2차 파싱: ezdxf 기반 세부 파싱 및 DB 적재."""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import ezdxf  # type: ignore
except ImportError:  # pragma: no cover
    ezdxf = None

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from packages.db.src.session import SessionLocal
from packages.db.src import models

logger = logging.getLogger(__name__)

STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
EZDXF_CACHE_DIR = Path(os.getenv("EZDXF_CACHE_DIR", ".cache/ezdxf"))
UNIT_INPUT = os.getenv("UNIT_INPUT", "mm")
UNIT_OUTPUT = os.getenv("UNIT_OUTPUT", "m")
INSUNITS_MAP = {
    0: "unitless",
    1: "inches",
    2: "feet",
    3: "miles",
    4: "millimeter",
    5: "centimeter",
    6: "meter",
}


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
        if dtype in ("TEXT", "MTEXT", "HATCH", "INSERT", "BLOCK", "DIMENSION", "ELLIPSE"):
            ins = getattr(entity.dxf, "insert", None) or getattr(entity.dxf, "center", None)
            if ins is not None:
                return f"POINT({ins[0]} {ins[1]})"
    except Exception:
        return None
    return None


def _entity_length(entity) -> float | None:
    try:
        return float(entity.length())
    except Exception:
        return None


def _poly_area(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 3:
        return None
    area = 0.0
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _entity_area(entity) -> float | None:
    dtype = entity.dxftype()
    try:
        if dtype == "HATCH":
            return float(entity.get_area())
        if dtype in ("LWPOLYLINE", "POLYLINE"):
            pts = list(entity.get_points("xy"))
            if not pts:
                return None
            return _poly_area([(float(x), float(y)) for x, y in pts])
        if dtype == "CIRCLE":
            r = getattr(entity.dxf, "radius", None)
            return float(3.141592653589793 * r * r) if r is not None else None
        if dtype == "ELLIPSE":
            major = getattr(entity.dxf, "major_axis", None)
            ratio = getattr(entity.dxf, "ratio", None)
            if major is not None and ratio is not None:
                import math

                return float(math.pi * (major.magnitude / 2.0) * (major.magnitude / 2.0) * ratio)
    except Exception:
        return None
    return None


def _entity_counts(doc) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for entity in doc.modelspace():
        counts[entity.dxftype()] += 1
    counts["layers"] = len(doc.layers)
    return counts


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _collect_document_metadata(doc) -> dict[str, Any]:
    insunits = doc.header.get("$INSUNITS", None)
    return {
        "section": "document",
        "filename": getattr(doc, "filename", None),
        "version": doc.dxfversion if hasattr(doc, "dxfversion") else None,
        "insunits": INSUNITS_MAP.get(insunits, insunits),
        "comment": getattr(doc, "comment", None),
    }


def _collect_header_metadata(doc) -> dict[str, Any]:
    header: dict[str, Any] = {}
    keys = []
    try:
        keys = list(doc.header.keys())
    except Exception:
        try:
            keys = list(doc.header)
        except Exception:
            keys = []

    for key in keys:
        if not isinstance(key, str) or not key.startswith("$"):
            continue
        try:
            header[key[1:]] = doc.header.get(key) if hasattr(doc.header, "get") else doc.header[key]
        except Exception:
            continue
    return {"section": "header", "header": header}


def _collect_table_layers(doc) -> list[dict[str, Any]]:
    layers = []
    for layer in doc.layers:
        layers.append(
            {
                "name": layer.dxf.name,
                "color": layer.color,
                "linetype": layer.dxf.linetype,
                "lineweight": layer.dxf.get("lineweight"),
                "plot": layer.dxf.get("plot"),
                "frozen": layer.is_frozen,
                "locked": layer.is_locked,
            }
        )
    return layers


def _collect_table_linetypes(doc) -> list[dict[str, Any]]:
    lts = []
    for ltype in doc.linetypes:
        lts.append(
            {
                "name": ltype.dxf.name,
                "description": ltype.dxf.description,
                "pattern_length": getattr(ltype.dxf, "pattern_length", None),
                "pattern": getattr(ltype.dxf, "pattern", None),
            }
        )
    return lts


def _collect_table_text_styles(doc) -> list[dict[str, Any]]:
    styles = []
    for style in doc.styles:
        # 일부 DXF에서는 없는 필드 접근 시 ezdxf가 예외를 던지므로 getattr로 안전 접근
        styles.append(
            {
                "name": style.dxf.name,
                "font": getattr(style.dxf, "font", None),
                "width_factor": getattr(style.dxf, "width_factor", None),
                "oblique": getattr(style.dxf, "oblique", None),
            }
        )
    return styles


def _collect_table_dim_styles(doc) -> list[dict[str, Any]]:
    dimstyles = []
    for dim in doc.dimstyles:
        dimstyles.append(
            {
                "name": dim.dxf.name,
                "arrow_size": dim.dxf.get("dimasz"),
                "extension": dim.dxf.get("dimexe"),
                "text_height": dim.dxf.get("dimtxt"),
                "unit_format": dim.dxf.get("dimlunit"),
                "tolerance": dim.dxf.get("dimtol"),
            }
        )
    return dimstyles


def _collect_block_reference_counts(doc) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for insert in doc.modelspace().query("INSERT"):
        name = getattr(insert.dxf, "name", None)
        if name:
            counts[name] += 1
    return counts


def _collect_table_blocks(doc, ref_counts: dict[str, int]) -> list[dict[str, Any]]:
    blocks = []
    for block in doc.blocks:
        blocks.append(
            {
                "name": block.name,
                "description": getattr(block, "description", None),
                "base_point": getattr(block.block, "dxf", None) and getattr(block.block.dxf, "base_point", None),
                "entity_count": len(block),
                "insert_count": ref_counts.get(block.name, 0),
            }
        )
    return blocks


def _collect_tables_metadata(doc) -> dict[str, Any]:
    ref_counts = _collect_block_reference_counts(doc)
    return {
        "section": "tables",
        "layers": _collect_table_layers(doc),
        "linetypes": _collect_table_linetypes(doc),
        "text_styles": _collect_table_text_styles(doc),
        "dim_styles": _collect_table_dim_styles(doc),
        "block_records": _collect_table_blocks(doc, ref_counts),
    }


def _collect_layouts_metadata(doc) -> dict[str, Any]:
    layouts = []
    for layout in doc.layouts:
        viewports = []
        try:
            viewports = [
                {
                    "handle": vp.dxf.handle,
                    "center": getattr(vp.dxf, "center", None),
                    "height": getattr(vp.dxf, "height", None),
                    "width": getattr(vp.dxf, "width", None),
                    "view_target": getattr(vp.dxf, "view_target_point", None),
                    "view_direction": getattr(vp.dxf, "view_direction_vector", None),
                }
                for vp in layout.viewports()
            ]
        except Exception:
            viewports = []
        layouts.append(
            {
                "name": layout.name,
                "scale": getattr(layout.dxf, "custom_print_scale", None) or getattr(layout, "get_plot_scale", lambda: None)(),
                "tab_order": getattr(layout.dxf, "taborder", None),
                "plot_layout_flags": getattr(layout.dxf, "plot_layout_flags", None),
                "unit_factor": getattr(layout.dxf, "plot_paper_units", None),
                "viewports": viewports,
            }
        )
    return {"section": "layouts", "layouts": layouts}


def _write_jsonl(path: Path, records: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for rec in records:
            fp.write(json.dumps(rec, ensure_ascii=False))
            fp.write("\n")


def _default_jsonl_path(src: Path) -> Path:
    return STORAGE_DERIVED_PATH / f"{src.stem}_meta.jsonl"


async def run(file_id: Optional[str] = None, src: Optional[Path] = None, jsonl_path: Optional[Path] = None) -> None:
    """DXF 파일을 파싱해 메타데이터를 JSONL로, 엔티티는 DB에 적재한다."""
    _ensure_ezdxf()
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)

    if isinstance(src, str):
        src = Path(src)
    if isinstance(jsonl_path, str):
        jsonl_path = Path(jsonl_path)

    if src is None:
        if file_id:
            async with SessionLocal() as session:
                file_row = await session.get(models.File, file_id)
                if not file_row or not file_row.path_dxf:
                    logger.error("file_id=%s에 대한 path_dxf가 없습니다. 변환 완료 후 파싱하세요.", file_id)
                    return
                src = Path(file_row.path_dxf)
                if not src.exists():
                    logger.error("DXF 파일이 존재하지 않습니다: %s", src)
                    return
        else:
            candidates = sorted(STORAGE_DERIVED_PATH.glob("*.dxf"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not candidates:
                logger.info("파싱할 DXF가 없습니다 (경로: %s)", STORAGE_DERIVED_PATH)
                return
            src = candidates[0]

    logger.info("DXF 2차 파싱 시작: %s", src)
    doc = ezdxf.readfile(src)
    counts = _entity_counts(doc)
    logger.info("DXF 카운트: %s", counts)

    metadata_records = [
        _collect_document_metadata(doc),
        _collect_header_metadata(doc),
        _collect_tables_metadata(doc),
        _collect_layouts_metadata(doc),
    ]
    meta_output = jsonl_path or _default_jsonl_path(src)
    _write_jsonl(meta_output, metadata_records)
    logger.info("메타데이터 JSONL 저장: %s", meta_output)

    if file_id is None:
        logger.warning("file_id가 없어 엔티티 DB 저장을 건너뜁니다. (파일: %s)", src)
        return

    async with SessionLocal() as session:
        try:
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
            logger.info("DXF 2차 파싱 완료: %s", file_id)
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("DB 저장 중 오류: %s", e)
            raise


def _entity_properties(entity) -> dict[str, Any]:
    dtype = entity.dxftype()
    props: dict[str, Any] = {
        "color": getattr(entity.dxf, "color", None),
        "linetype": getattr(entity.dxf, "linetype", None),
        "lineweight": getattr(entity.dxf, "lineweight", None),
        "thickness": getattr(entity.dxf, "thickness", None),
    }

    if dtype in ("LINE", "POLYLINE", "LWPOLYLINE"):
        props["points"] = [list(pt) for pt in getattr(entity, "points", lambda: [])()] if hasattr(entity, "points") else list(entity.get_points("xy"))
    if dtype == "CIRCLE":
        props["center"] = list(getattr(entity.dxf, "center", ()))
        props["radius"] = getattr(entity.dxf, "radius", None)
    if dtype == "ARC":
        props["center"] = list(getattr(entity.dxf, "center", ()))
        props["radius"] = getattr(entity.dxf, "radius", None)
        props["start_angle"] = getattr(entity.dxf, "start_angle", None)
        props["end_angle"] = getattr(entity.dxf, "end_angle", None)
    if dtype in ("TEXT", "MTEXT"):
        props["text"] = getattr(entity.dxf, "text", None)
        props["height"] = getattr(entity.dxf, "height", None) or getattr(entity.dxf, "char_height", None)
        props["style"] = getattr(entity.dxf, "style", None)
    if dtype == "DIMENSION":
        props["block"] = getattr(entity.dxf, "block", None)
        props["definition_point"] = list(getattr(entity.dxf, "definition_point", ()))
    if dtype == "INSERT":
        props["name"] = getattr(entity.dxf, "name", None)
        props["insert"] = list(getattr(entity.dxf, "insert", ()))
        props["rotation"] = getattr(entity.dxf, "rotation", None)
        props["xscale"] = getattr(entity.dxf, "xscale", None)
        props["yscale"] = getattr(entity.dxf, "yscale", None)
        props["zscale"] = getattr(entity.dxf, "zscale", None)

    return {k: v for k, v in props.items() if v not in (None, [], {})}
