"""Start RQ worker for Sourcebook ingest queue.

Usage (from apps/api, with Redis up):

    uv run python -m app.workers.rq_worker

On macOS, RQ's default forking worker crashes (ObjC fork safety).
We use SimpleWorker there so jobs actually run.
"""

from __future__ import annotations

import os
import platform

from redis import Redis
from rq import SimpleWorker, Worker

from app.config import settings
from app.logging_config import get_logger, setup_logging
from app.workers.queue import INGEST_QUEUE_NAME


def main() -> None:
    # Helps some native libs if fork is used on macOS
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    setup_logging(level=settings.log_level, json_logs=settings.log_json)
    log = get_logger("sourcebook.worker")

    redis_conn = Redis.from_url(settings.redis_url)

    # SimpleWorker: no fork — required for reliable jobs on macOS
    worker_cls = SimpleWorker if platform.system() == "Darwin" else Worker
    worker = worker_cls([INGEST_QUEUE_NAME], connection=redis_conn)

    log.info(
        "worker_starting",
        extra={
            "event": "worker_start",
            "queue": INGEST_QUEUE_NAME,
            "worker_class": worker_cls.__name__,
        },
    )
    print(
        f"Starting {worker_cls.__name__} on queue={INGEST_QUEUE_NAME!r} "
        f"redis={settings.redis_url!r}"
    )
    # with_scheduler only on Worker that supports it; SimpleWorker may not
    try:
        worker.work(with_scheduler=True)
    except TypeError:
        worker.work()


if __name__ == "__main__":
    main()
