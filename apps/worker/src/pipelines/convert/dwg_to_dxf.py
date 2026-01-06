"""DWG 업로드 감지 후 ODA 변환 실행 파이프라인."""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
import shutil

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from packages.db.src.session import SessionLocal

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[4]))
ODA_CONVERTER_PATH = Path(os.getenv("ODA_CONVERTER_PATH", "tools/oda/ODAFileConverter"))
ODA_DOCKER_IMAGE = os.getenv("ODA_DOCKER_IMAGE")
ODA_CONTAINER_WORKDIR = os.getenv("ODA_CONTAINER_WORKDIR", "/data/storage")
ODA_CONVERTER_PATH_IN_IMAGE = os.getenv("ODA_CONVERTER_PATH_IN_IMAGE", "/usr/bin/ODAFileConverter")
ODA_VOLUME_NAME = os.getenv("ODA_VOLUME_NAME", "laika_storage_data")
STORAGE_ORIGINAL_PATH = Path(os.getenv("STORAGE_ORIGINAL_PATH", "storage/original"))
STORAGE_DERIVED_PATH = Path(os.getenv("STORAGE_DERIVED_PATH", "storage/derived"))


async def convert_dwg_to_dxf(src: Path, dest_dir: Path) -> Path:
    """ODAFileConverter(또는 docker 모드)로 DWG를 DXF로 변환한다."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_path = dest_dir / f"{src.stem}.dxf"

    src_abs = src.resolve()
    dest_abs = dest_dir.resolve()
    input_dir = src_abs.parent  # ODAFileConverter는 디렉터리 단위로 변환

    if ODA_DOCKER_IMAGE:
        if not shutil.which("docker"):
            raise RuntimeError("docker CLI가 없습니다. worker 컨테이너에 docker-cli를 설치하고 /var/run/docker.sock을 마운트하세요.")

        container_root = Path(ODA_CONTAINER_WORKDIR)
        try:
            src_rel = src_abs.relative_to(container_root)
            dest_rel = dest_abs.relative_to(container_root)
            input_dir_rel = input_dir.relative_to(container_root)
        except Exception as exc:
            raise RuntimeError(f"경로 매핑 실패: src={src_abs}, dest={dest_abs}, root={container_root}") from exc

        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ODA_VOLUME_NAME}:{container_root}",
            "-w",
            str(container_root),
            ODA_DOCKER_IMAGE,
            str(container_root / input_dir_rel),
            str(container_root / dest_rel),
            "ACAD2018",
            "DXF",
            "1",
            "1",
        ]
    else:
        cmd = [
            str(ODA_CONVERTER_PATH),
            str(src_abs),
            str(dest_abs),
            "ACAD2018",
            "DXF",
            "1",
            "1",
        ]

    logger.info("ODA 변환 실행: cmd=%s", " ".join(str(c) for c in cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"ODA 변환 시간 초과: {src}")
    stdout_text = stdout.decode(errors="ignore")
    if proc.returncode != 0:
        logger.error("ODA 변환 실패 rc=%s output=%s", proc.returncode, stdout_text)
        raise RuntimeError(f"ODA 변환 실패: {src}")

    if not output_path.exists():
        logger.error("ODA 변환 완료했지만 출력 DXF가 없습니다. stdout=%s", stdout_text)
        raise RuntimeError(f"ODA 변환 결과 파일이 없습니다: {output_path}")

    logger.info("ODA 변환 성공: %s -> %s", src, output_path)
    return output_path


async def run(src: Optional[Path] = None, file_id: Optional[str] = None) -> Optional[Path]:
    """단일 DWG를 DXF로 변환.

    file_id가 주어지면 files.path_dxf와 conversion_logs(status=pending/success/fail)를 갱신한다.
    """
    if isinstance(src, str):
        src = Path(src)

    STORAGE_ORIGINAL_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_DERIVED_PATH.mkdir(parents=True, exist_ok=True)

    if src is None:
        candidates = sorted(STORAGE_ORIGINAL_PATH.glob("*.dwg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            logger.info("변환할 DWG가 없습니다 (원본 경로: %s)", STORAGE_ORIGINAL_PATH)
            return None
        src = candidates[0]

    dest_path = STORAGE_DERIVED_PATH / f"{src.stem}.dxf"

    if file_id:
        async with SessionLocal() as session:
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at)
                    values (:file_id, 'pending', now())
                    """
                ),
                {"file_id": file_id},
            )
            await session.commit()

    try:
        await convert_dwg_to_dxf(src, STORAGE_DERIVED_PATH)
    except Exception as e:
        if file_id:
            async with SessionLocal() as session:
                await session.execute(
                    text(
                        """
                        insert into conversion_logs (file_id, status, message, started_at, finished_at)
                        values (:file_id, 'failed', :msg, now(), now())
                        """
                    ),
                    {"file_id": file_id, "msg": str(e)},
                )
                await session.commit()
        raise

    if file_id:
        async with SessionLocal() as session:
            params = {"file_id": file_id, "path_dxf": str(dest_path)}
            await session.execute(
                text("update files set path_dxf = :path_dxf where id = :file_id"),
                params,
            )
            await session.execute(
                text(
                    """
                    insert into conversion_logs (file_id, status, started_at, finished_at)
                    values (:file_id, 'success', now(), now())
                    """
                ),
                params,
            )
            await session.commit()

    return dest_path
