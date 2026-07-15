from __future__ import annotations

import uuid

from redis import Redis
from rq import Queue, Retry

from app.config import settings

INGEST_QUEUE_NAME = "sourcebook-ingest"


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def get_ingest_queue() -> Queue:
    return Queue(INGEST_QUEUE_NAME, connection=get_redis())


def enqueue_document_ingest(document_id: uuid.UUID, user_id: uuid.UUID):
    """
    Enqueue background ingest. Returns RQ Job.

    Retries: 3 attempts with backoff (RQ Retry).
    """
    queue = get_ingest_queue()
    return queue.enqueue(
        "app.workers.ingest_jobs.process_document_ingest",
        str(document_id),
        str(user_id),
        job_timeout=settings.ingest_job_timeout_seconds,
        result_ttl=3600,
        failure_ttl=86400,
        retry=Retry(max=3, interval=[10, 30, 60]),
    )


def redis_ping() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


def ingest_worker_count() -> int:
    """Number of RQ workers listening on the ingest queue (0 = jobs would
    sit in 'queued' forever). Returns 0 on errors so callers fall back."""
    from rq import Worker

    try:
        queue = get_ingest_queue()
        return Worker.count(connection=queue.connection, queue=queue)
    except Exception:
        return 0
