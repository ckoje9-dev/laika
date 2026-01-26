"""Parser configuration from environment variables."""
import os
from pathlib import Path

# Node.js binary path
NODE_BIN = os.getenv("DXF_PARSER_NODE_BIN", "node")

# DXF parser library path
DXF_PARSER_LIB = Path(
    os.getenv(
        "DXF_PARSER_LIB",
        Path(__file__).resolve().parents[3] / "apps" / "worker" / "src" / "lib" / "node_modules" / "dxf-parser" / "dist" / "dxf-parser.js",
    )
)

# Parsing timeout in seconds
PARSE1_TIMEOUT = int(os.getenv("DXF_PARSER_TIMEOUT", "120"))
