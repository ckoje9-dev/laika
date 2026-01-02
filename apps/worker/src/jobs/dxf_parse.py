"""DXF 파싱 및 메타/엔티티 적재 잡."""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

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
            pts = [(p[0], p[1]) for p in entity.get_points("xy")]
            if entity.closed or (pts and pts[0] != pts[-1]):
                return _poly_area(pts)
        if dtype == "CIRCLE":
            r = getattr(entity.dxf, "radius", None)
            if r is not None:
                return float(3.141592653589793 * r * r)
    except Exception:
        return None
    return None


def _entity_common_props(entity) -> dict[str, Any]:
    return {
        "color_index": getattr(entity.dxf, "color", None),
        "true_color": getattr(entity.dxf, "true_color", None),
        "linetype": getattr(entity.dxf, "linetype", None),
        "lineweight": getattr(entity.dxf, "lineweight", None),
    }


def _entity_properties(entity) -> dict[str, Any]:
    dtype = entity.dxftype()
    props: dict[str, Any] = _entity_common_props(entity)

    if dtype == "LINE":
        props.update(
            {
                "start": list(entity.dxf.start) if hasattr(entity.dxf, "start") else None,
                "end": list(entity.dxf.end) if hasattr(entity.dxf, "end") else None,
            }
        )
    elif dtype in ("LWPOLYLINE", "POLYLINE"):
        pts = [list(p) for p in entity.get_points("xy")]
        props.update(
            {
                "vertices": pts,
                "is_closed": bool(getattr(entity, "closed", False)),
                "width": getattr(entity.dxf, "const_width", None),
            }
        )
    elif dtype == "CIRCLE":
        props.update(
            {
                "center": list(getattr(entity.dxf, "center", []) or []),
                "radius": getattr(entity.dxf, "radius", None),
                "diameter": getattr(entity.dxf, "radius", None) and getattr(entity.dxf, "radius") * 2,
            }
        )
    elif dtype == "ARC":
        props.update(
            {
                "center": list(getattr(entity.dxf, "center", []) or []),
                "radius": getattr(entity.dxf, "radius", None),
                "start_angle": getattr(entity.dxf, "start_angle", None),
                "end_angle": getattr(entity.dxf, "end_angle", None),
            }
        )
    elif dtype == "ELLIPSE":
        props.update(
            {
                "center": list(getattr(entity.dxf, "center", []) or []),
                "major_axis": list(getattr(entity.dxf, "major_axis", []) or []),
                "ratio": getattr(entity.dxf, "ratio", None),
                "start_param": getattr(entity.dxf, "start_param", None),
                "end_param": getattr(entity.dxf, "end_param", None),
            }
        )
    elif dtype == "HATCH":
        props.update(
            {
                "pattern": getattr(entity.dxf, "pattern_name", None),
                "scale": getattr(entity.dxf, "pattern_scale", None),
                "rotation": getattr(entity.dxf, "pattern_angle", None),
                "paths": [path.type for path in getattr(entity, "paths", [])],
            }
        )
    elif dtype == "TEXT":
        props.update(
            {
                "text": entity.plain_text() if hasattr(entity, "plain_text") else getattr(entity.dxf, "text", None),
                "insert": getattr(entity.dxf, "insert", None) and list(entity.dxf.insert),
                "rotation": getattr(entity.dxf, "rotation", None),
                "alignment": getattr(entity.dxf, "halign", None),
                "height": getattr(entity.dxf, "height", None),
                "style": getattr(entity.dxf, "style", None),
            }
        )
    elif dtype == "MTEXT":
        props.update(
            {
                "text": getattr(entity.dxf, "text", None),
                "insert": getattr(entity.dxf, "insert", None) and list(entity.dxf.insert),
                "rotation": getattr(entity.dxf, "rotation", None),
                "width": getattr(entity.dxf, "width", None),
                "line_spacing": getattr(entity.dxf, "line_spacing_factor", None),
                "style": getattr(entity.dxf, "style", None),
            }
        )
    elif dtype == "DIMENSION":
        props.update(
            {
                "dimension_type": getattr(entity.dxf, "dimtype", None),
                "measurement": getattr(entity, "measurement", None),
                "defpoint": getattr(entity.dxf, "defpoint", None) and list(entity.dxf.defpoint),
                "text_midpoint": getattr(entity.dxf, "text_midpoint", None) and list(entity.dxf.text_midpoint),
                "block": getattr(entity.dxf, "block", None),
            }
        )
    elif dtype == "INSERT":
        attrs = []
        for attr in getattr(entity, "attribs", []):
            attrs.append(
                {
                    "tag": getattr(attr.dxf, "tag", None),
                    "value": getattr(attr.dxf, "text", None),
                    "position": getattr(attr.dxf, "insert", None) and list(attr.dxf.insert),
                    "invisible": getattr(attr.dxf, "invisible", None),
                }
            )
        props.update(
            {
                "name": getattr(entity.dxf, "name", None),
                "insert": getattr(entity.dxf, "insert", None) and list(entity.dxf.insert),
                "scale": getattr(entity.dxf, "scale", None) and list(entity.dxf.scale),
                "rotation": getattr(entity.dxf, "rotation", None),
                "attributes": attrs,
            }
        )
    elif dtype == "BLOCK":
        props.update(
            {
                "name": getattr(entity.dxf, "name", None),
                "base_point": getattr(entity.dxf, "base_point", None) and list(entity.dxf.base_point),
            }
        )
    return props


def _entity_counts(doc) -> dict[str, int]:
    msp = doc.modelspace()
    entity_types = [
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "CIRCLE",
        "ARC",
        "ELLIPSE",
        "TEXT",
        "MTEXT",
        "HATCH",
        "DIMENSION",
        "INSERT",
        "BLOCK",
    ]
    counts = {etype: len(msp.query(etype)) for etype in entity_types}
    counts["layers"] = len(doc.layers)
    return counts


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for rec in records:
            fp.write(json.dumps(_json_safe(rec), ensure_ascii=False))
            fp.write("\n")


def _json_safe(value: Any) -> Any:
    """ezdxf Vec3 등 JSON 직렬화 불가 객체를 안전하게 변환."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if hasattr(value, "x") and hasattr(value, "y"):
        coords = [float(getattr(value, "x", 0.0)), float(getattr(value, "y", 0.0))]
        if hasattr(value, "z"):
            coords.append(float(getattr(value, "z", 0.0)))
        return coords
    return str(value)


def _collect_document_metadata(doc) -> dict[str, Any]:
    return {
        "section": "document",
        "dxf_version": doc.dxfversion,
    }


def _collect_header_metadata(doc) -> dict[str, Any]:
    header = doc.header
    return {
        "section": "header",
        "values": {
            "$INSUNITS": header.get("$INSUNITS"),
            "$EXTMIN": header.get("$EXTMIN"),
            "$EXTMAX": header.get("$EXTMAX"),
            "$LIMMIN": header.get("$LIMMIN"),
            "$LIMMAX": header.get("$LIMMAX"),
            "$ANGBASE": header.get("$ANGBASE"),
            "$ANGDIR": header.get("$ANGDIR"),
        },
    }


def _collect_table_layers(doc) -> list[dict[str, Any]]:
    layers = []
    for layer in doc.layers:
        plottable = getattr(layer, "is_plottable", None)
        if callable(plottable):
            try:
                plottable = plottable()
            except Exception:
                plottable = None
        elif plottable is None:
            plottable = getattr(getattr(layer, "dxf", None), "plot", None)
        layers.append(
            {
                "name": layer.dxf.name,
                "color_index": layer.dxf.color,
                "true_color": getattr(layer.dxf, "true_color", None),
                "linetype": layer.dxf.linetype,
                "is_on": not bool(layer.is_off()),
                "is_locked": bool(getattr(layer, "is_locked", False)),
                "is_plottable": bool(plottable) if plottable is not None else None,
            }
        )
    return layers


def _collect_table_linetypes(doc) -> list[dict[str, Any]]:
    ltypes = []
    for lt in doc.linetypes:
        pattern = None
        try:
            pattern = list(lt.pattern_tags())
        except Exception:
            try:
                pattern = list(lt.pattern)
            except Exception:
                pattern = None
        ltypes.append(
            {
                "name": lt.dxf.name,
                "length": getattr(lt.dxf, "length", None),
                "pattern": pattern,
            }
        )
    return ltypes


def _collect_table_text_styles(doc) -> list[dict[str, Any]]:
    styles = []
    for style in doc.styles:
        styles.append(
            {
                "name": style.dxf.name,
                "font": getattr(style.dxf, "font", None) or getattr(style.dxf, "filename", None),
                "height": getattr(style.dxf, "height", None),
                "width_factor": getattr(style.dxf, "width", None),
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


def _default_jsonl_path(src: Path) -> Path:
    return STORAGE_DERIVED_PATH / f"{src.stem}_meta.jsonl"


async def run(file_id: Optional[str] = None, src: Optional[Path] = None, jsonl_path: Optional[Path] = None) -> None:
    """DXF 파일을 파싱해 1~3번 메타데이터는 JSONL, 4~5번 엔티티는 DB에 적재."""
    _ensure_ezdxf()
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)

    if src is None:
        # file_id가 주어지면 DB에 기록된 path_dxf를 사용해 정확한 파일을 파싱
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

    logger.info("DXF 파싱 시작: %s", src)
    doc = ezdxf.readfile(src)
    counts = _entity_counts(doc)
    logger.info("DXF 카운트: %s", counts)

    # 1~3 + 5 메타데이터 JSONL 기록
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

    msp = doc.modelspace()
    entities: list[models.DxfEntityRaw] = []
    for entity in msp:
        dtype = entity.dxftype()
        if dtype not in (
            "LINE",
            "LWPOLYLINE",
            "POLYLINE",
            "CIRCLE",
            "ARC",
            "ELLIPSE",
            "TEXT",
            "MTEXT",
            "HATCH",
            "DIMENSION",
            "INSERT",
            "BLOCK",
        ):
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
            properties=_entity_properties(entity),
        )
        entities.append(rec)

    async with SessionLocal() as session:
        try:
            # 기존 파싱 결과는 제거하고 다시 적재
            await session.execute(text("delete from dxf_entities_raw where file_id = :file_id"), {"file_id": file_id})
            session.add_all(entities)
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
            logger.info("DXF 파싱 완료 및 DB 저장: %s (entities=%s)", file_id, len(entities))
        except SQLAlchemyError as e:
            await session.rollback()
            logger.exception("DB 저장 중 오류: %s", e)
            raise
