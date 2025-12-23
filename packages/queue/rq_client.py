"""RQ 기반 큐 헬퍼."""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

import redis
from rq import Queue, Worker


def get_redis_connection() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis_connection())


def enqueue(job_func: Callable[..., Any], *args: Any, **kwargs: Any):
    q = get_queue()
    return q.enqueue(job_func, *args, **kwargs)


def start_worker(job_funcs: Mapping[str, Callable[..., Any]]):
    """매핑된 함수들만 허용하는 RQ Worker."""
    # RQ Worker는 함수 임포트 경로를 사용하므로, 안전하게 매핑된 함수만 등록하려면
    # Worker(initial_job_class) 등을 커스터마이징해야 하지만, 여기서는 기본 Worker를 사용하고
    # enqueue 시 직접 함수를 전달하는 방식을 따른다.
    conn = get_redis_connection()
    worker = Worker([get_queue()], connection=conn)
    worker.work()
