"""1차 DXF 파싱: Node dxf-parser를 호출해 섹션/엔티티 JSON을 생성한다."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from packages.db.src import models
from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)

STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
NODE_BIN = os.getenv("DXF_PARSER_NODE_BIN", "node")
DXF_PARSER_LIB = Path(
    os.getenv(
        "DXF_PARSER_LIB",
        Path(__file__).resolve().parents[2] / "lib" / "dxf-parser" / "commonjs" / "index.js",
    )
)
PARSE1_TIMEOUT = int(os.getenv("DXF_PARSER_TIMEOUT", "120"))


async def _node_parse(src: Path, output_path: Path) -> None:
    """node subprocess로 dxf-parser를 호출해 JSON으로 저장."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = r"""
const fs = require('fs');
const ParserMod = require(process.env.DXF_PARSER_LIB);
const Parser = ParserMod.default || ParserMod;

async function main() {
  const input = process.env.DXF_PARSE_INPUT;
  const output = process.env.DXF_PARSE_OUTPUT;
  if (!input || !output) {
    throw new Error("DXF_PARSE_INPUT or OUTPUT missing");
  }
  const text = fs.readFileSync(input, 'utf8');
  const parser = new Parser();
  const data = parser.parseSync(text);
  const result = {
    sections: {
      header: data.header || null,
      tables: data.tables || null,
      blocks: data.blocks || null,
      objects: data.objects || null,
      classes: data.classes || null,
      thumbnail: data.thumbnail || null,
    },
    entities: data.entities || [],
    metadata: {
      version: (data.header && data.header.$ACADVER) || null,
      generated_at: new Date().toISOString(),
      source: input,
    },
  };
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
}

main().catch((err) => {
  console.error(err?.stack || err?.message || err);
  process.exit(1);
});
"""
    env = os.environ.copy()
    env["DXF_PARSER_LIB"] = str(DXF_PARSER_LIB)
    env["DXF_PARSE_INPUT"] = str(src)
    env["DXF_PARSE_OUTPUT"] = str(output_path)
    cmd = [NODE_BIN, "-e", script]
    logger.info("1차 파싱(Node) 실행: %s input=%s output=%s", " ".join(cmd), src, output_path)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=PARSE1_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"dxf-parser(Node) 시간 초과: {src}")
    if proc.returncode != 0:
        out = stdout.decode(errors="ignore") if stdout else ""
        raise RuntimeError(f"dxf-parser(Node) 실패: rc={proc.returncode} output={out}")


async def _resolve_src(file_id: Optional[str], src: Optional[Path]) -> Optional[Path]:
    if src is not None:
        return src
    if not file_id:
        return None
    async with SessionLocal() as session:
        file_row = await session.get(models.File, file_id)
        if not file_row:
            logger.error("file not found: %s", file_id)
            return None
        if not file_row.path_dxf and file_row.path_original:
            file_row.path_dxf = file_row.path_original
        if not file_row.path_dxf:
            logger.error("DXF 경로가 없습니다. file_id=%s", file_id)
            return None
        return Path(file_row.path_dxf)


async def run(file_id: Optional[str] = None, src: Optional[Path] = None, output_path: Optional[Path] = None) -> Optional[Path]:
    """DXF를 1차 파싱해 JSON을 생성한다."""
    if isinstance(src, str):
        src = Path(src)
    if isinstance(output_path, str):
        output_path = Path(output_path)

    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)
    src_path = await _resolve_src(file_id, src)
    if src_path is None:
        return None
    out_path = output_path or STORAGE_DERIVED_PATH / f"{src_path.stem}_parse1.json"

    try:
        await _node_parse(src_path, out_path)
        logger.info("1차 파싱 완료: %s -> %s", src_path, out_path)
    except Exception:
        logger.exception("1차 파싱 실패: %s", src_path)
        if file_id:
            async with SessionLocal() as session:
                await session.execute(
                    text(
                        """
                        insert into conversion_logs (file_id, status, started_at, finished_at, message)
                        values (:file_id, 'failed', now(), now(), :msg)
                        """
                    ),
                    {"file_id": file_id, "msg": "parse1 failed"},
                )
                await session.commit()
        return None

    # dxf-parser 결과를 DB에 적재 (type/layer/properties만 저장)
    if file_id:
        try:
            with out_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            data = {}

        sections = data.get("sections") if isinstance(data, dict) else {}
        if not isinstance(sections, dict):
            sections = {}
        entities = data.get("entities") if isinstance(data, dict) else None
        if not isinstance(entities, list):
            entities = []

        layer_names = set()
        tables = sections.get("tables") if isinstance(sections, dict) else None
        if isinstance(tables, dict):
            raw_layers = (
                tables.get("layer", {}).get("layers")
                or tables.get("layers")
                or tables.get("layer")
            )
            if isinstance(raw_layers, dict):
                raw_layers = raw_layers.get("layers") or list(raw_layers.values())
            if isinstance(raw_layers, list):
                for l in raw_layers:
                    name = l.get("name") if isinstance(l, dict) else l
                    if name:
                        layer_names.add(str(name))
        if not layer_names:
            for ent in entities:
                if not isinstance(ent, dict):
                    continue
                layer = ent.get("layer") or ent.get("layerName")
                if layer:
                    layer_names.add(str(layer))

        async with SessionLocal() as session:
            try:
                await session.execute(text("delete from dxf_parse_sections where file_id = :file_id"), {"file_id": file_id})
                session.add(
                    models.DxfParseSection(
                        file_id=file_id,
                        header=sections.get("header"),
                        classes=sections.get("classes"),
                        tables=sections.get("tables"),
                        blocks=sections.get("blocks"),
                        entities=entities,
                        objects=sections.get("objects"),
                        thumbnail=sections.get("thumbnail"),
                    )
                )
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
                        "layers": len(layer_names),
                        "entities": len(entities),
                        "file_id": file_id,
                    },
                )
                await session.execute(
                    text(
                        """
                        insert into conversion_logs (file_id, status, started_at, finished_at, layer_count, entity_count, message)
                        values (:file_id, 'success', now(), now(), :layers, :entities, :path)
                        """
                    ),
                    {
                        "file_id": file_id,
                        "layers": len(layer_names),
                        "entities": len(entities),
                        "path": str(out_path),
                    },
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                logger.warning("parse1 DB 적재 실패: file_id=%s", file_id)

    return out_path
