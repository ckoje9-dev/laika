"""File path generation helpers."""
from pathlib import Path
from .config import STORAGE_ORIGINAL_PATH, STORAGE_DERIVED_PATH


def get_original_path(filename: str) -> Path:
    """Generate path for original uploaded files.

    Args:
        filename: Name of the uploaded file

    Returns:
        Full path in original storage directory
    """
    return STORAGE_ORIGINAL_PATH / filename


def get_derived_path(filename: str, suffix: str) -> Path:
    """Generate path for derived files (parsed, converted).

    Args:
        filename: Original filename
        suffix: Suffix to append (e.g., 'parse1', 'converted')

    Returns:
        Full path in derived storage directory with suffix
    """
    stem = Path(filename).stem
    extension = Path(filename).suffix or ""
    return STORAGE_DERIVED_PATH / f"{stem}_{suffix}{extension}"


def ensure_storage_dirs() -> None:
    """Create storage directories if they don't exist."""
    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)
