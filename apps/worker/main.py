"""비동기 파이프라인 워커 엔트리포인트.

사용 예시:
    python -m apps.worker.main run dwg_to_dxf
    python -m apps.worker.main run dxf_parse
"""
import asyncio
import logging
import sys
from argparse import ArgumentParser, Namespace

from apps.worker.src.jobs import (
    dwg_to_dxf,
    dxf_parse,
    semantic_build,
    index_project,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("worker")


JOB_MAP = {
    "dwg_to_dxf": dwg_to_dxf.run,
    "dxf_parse": dxf_parse.run,
    "semantic_build": semantic_build.run,
    "index_project": index_project.run,
}


def parse_args(argv: list[str]) -> Namespace:
    parser = ArgumentParser(prog="laika-worker")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="단일 잡 실행")
    run.add_argument("job", choices=JOB_MAP.keys())

    return parser.parse_args(argv)


async def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.command == "run":
        job = JOB_MAP[args.job]
        logger.info("starting job '%s'", args.job)
        await job()
        logger.info("finished job '%s'", args.job)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
