"""DXF 파싱 및 Raw Entity 저장 잡."""
import logging
import os
from pathlib import Path
from typing import Optional

try:
    import ezdxf  # type: ignore
except ImportError:  # pragma: no cover - 라이브러리 미설치 시 런타임에 확인
    ezdxf = None

logger = logging.getLogger(__name__)

STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))
EZDXF_CACHE_DIR = Path(os.getenv("EZDXF_CACHE_DIR", ".cache/ezdxf"))


def _ensure_ezdxf():
    if ezdxf is None:
        raise RuntimeError("ezdxf가 설치되어 있지 않습니다. `pip install ezdxf` 후 재시도하세요.")
    os.environ.setdefault("EZDXF_CACHE_DIR", str(EZDXF_CACHE_DIR))
    EZDXF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def extract_counts(doc) -> dict:
    msp = doc.modelspace()
    entity_types = ["LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT", "HATCH", "INSERT"]
    counts = {etype: len(msp.query(etype)) for etype in entity_types}
    counts["layers"] = len(doc.layers)
    return counts


async def run(src: Optional[Path] = None) -> None:
    """단일 DXF 파일을 파싱하고 엔티티 카운트/레이어 정보를 로그로 남긴다.

    실제 환경에서는 DB 저장 로직으로 교체한다.
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
    logger.info("DXF 파싱 완료: %s | %s", src.name, counts)
    # TODO: counts 및 엔티티 데이터를 DB에 저장
