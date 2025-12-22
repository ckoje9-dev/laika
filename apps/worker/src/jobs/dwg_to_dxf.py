"""DWG 업로드 감지 후 ODA 변환 실행 잡."""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[4]))
ODA_CONVERTER_PATH = Path(os.getenv("ODA_CONVERTER_PATH", "tools/oda/ODAFileConverter"))
ODA_DOCKER_IMAGE = os.getenv("ODA_DOCKER_IMAGE")
ODA_CONTAINER_WORKDIR = os.getenv("ODA_CONTAINER_WORKDIR", "/data")
STORAGE_ORIGINAL_PATH = Path(os.getenv("STORAGE_ORIGINAL_PATH", "storage/original"))
STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))


async def convert_dwg_to_dxf(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_path = dest_dir / f"{src.stem}.dxf"

    # 컨테이너 실행 경로 대비를 위해 project root 상대 경로로 변환
    src_abs = src.resolve()
    dest_abs = dest_dir.resolve()

    if ODA_DOCKER_IMAGE:
        project_root = PROJECT_ROOT.resolve()
        try:
            src_rel = src_abs.relative_to(project_root)
            dest_rel = dest_abs.relative_to(project_root)
        except ValueError as exc:
            raise RuntimeError("src/dest는 PROJECT_ROOT 하위여야 컨테이너 실행이 가능합니다.") from exc

        converter_in_container = Path(ODA_CONTAINER_WORKDIR) / ODA_CONVERTER_PATH
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{project_root}:{ODA_CONTAINER_WORKDIR}",
            "-w",
            str(ODA_CONTAINER_WORKDIR),
            ODA_DOCKER_IMAGE,
            str(converter_in_container),
            str(Path(ODA_CONTAINER_WORKDIR) / src_rel),
            str(Path(ODA_CONTAINER_WORKDIR) / dest_rel),
            "ACAD2018",  # 출력 DWG/DXF 버전
            "DXF",       # 출력 포맷
            "1",         # 재귀 처리 (1=켜기)
            "1",         # 로그 레벨 (1=기본)
        ]
    else:
        cmd = [
            str(ODA_CONVERTER_PATH),
            str(src_abs),
            str(dest_abs),
            "ACAD2018",  # 출력 DWG/DXF 버전
            "DXF",       # 출력 포맷
            "1",         # 재귀 처리 (1=켜기)
            "1",         # 로그 레벨 (1=기본)
        ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        logger.error("ODA 변환 실패 rc=%s output=%s", proc.returncode, stdout.decode(errors="ignore"))
        raise RuntimeError(f"ODA 변환 실패: {src}")

    logger.info("ODA 변환 성공: %s -> %s", src, output_path)
    return output_path


async def run(src: Optional[Path] = None) -> None:
    """단일 DWG를 DXF로 변환.

    실제 환경에서는 큐/이벤트에서 src 경로를 받도록 대체한다.
    """
    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)

    if src is None:
        # 데모용: 원본 폴더에서 가장 최근 DWG 하나를 선택
        candidates = sorted(STORAGE_ORIGINAL_PATH.glob("*.dwg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            logger.info("변환할 DWG가 없습니다 (원본 경로: %s)", STORAGE_ORIGINAL_PATH)
            return
        src = candidates[0]

    await convert_dwg_to_dxf(src, STORAGE_DERIVED_PATH)
