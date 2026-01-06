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

    if file_id:
        async with SessionLocal() as session:
            try:
                await session.execute(
                    text(
                        """
                        insert into conversion_logs (file_id, status, started_at, finished_at, message)
                        values (:file_id, 'success', now(), now(), :path)
                        """
                    ),
                    {"file_id": file_id, "path": str(out_path)},
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
                logger.warning("parse1 로그 기록 실패: file_id=%s", file_id)
    return out_path
