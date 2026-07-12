"""Structured logging setup for Sourcebook API and workers."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Propagated across the request for correlation
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

_EXTRA_KEYS = (
    "request_id",
    "user_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "document_id",
    "job_id",
    "workspace_id",
    "event",
)


class ContextFilter(logging.Filter):
    """Inject request/user id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            rid = request_id_ctx.get()
            if rid:
                record.request_id = rid  # type: ignore[attr-defined]
        if not getattr(record, "user_id", None):
            uid = user_id_ctx.get()
            if uid:
                record.user_id = uid  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in _EXTRA_KEYS:
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None) or "-"
        base = f"{record.levelname} [{rid}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure root + uvicorn loggers once at process start."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())
    root.addHandler(handler)

    # Align common library loggers
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "rq.worker"):
        lib = logging.getLogger(name)
        lib.handlers.clear()
        lib.propagate = True
        lib.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quieter SQL by default
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """Build extra= dict for logger calls (only non-None values)."""
    return {k: v for k, v in kwargs.items() if v is not None}
