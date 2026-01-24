"""Node.js subprocess wrapper for DXF parsing."""
import asyncio
import logging
import os
from pathlib import Path

from .config import NODE_BIN, DXF_PARSER_LIB, PARSE1_TIMEOUT

logger = logging.getLogger(__name__)


async def parse_dxf(src: Path, output_path: Path) -> None:
    """Parse DXF file using Node.js dxf-parser subprocess.

    Args:
        src: Source DXF file path
        output_path: Output JSON file path

    Raises:
        RuntimeError: If parsing fails or times out
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Embedded Node.js script for parsing
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

    # Prepare environment
    env = os.environ.copy()
    env["DXF_PARSER_LIB"] = str(DXF_PARSER_LIB)
    env["DXF_PARSE_INPUT"] = str(src)
    env["DXF_PARSE_OUTPUT"] = str(output_path)

    cmd = [NODE_BIN, "-e", script]
    logger.info("1차 파싱(Node) 실행: input=%s output=%s", src, output_path)

    # Execute subprocess
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

    logger.info("파싱 완료: %s -> %s", src, output_path)
