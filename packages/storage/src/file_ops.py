"""File I/O operations."""
import json
from pathlib import Path
from typing import Any


async def save_json(path: Path, data: Any) -> None:
    """Save data as JSON file.

    Args:
        path: Target file path
        data: Data to serialize as JSON
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def load_json(path: Path) -> Any:
    """Load JSON file.

    Args:
        path: Source file path

    Returns:
        Deserialized JSON data
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
