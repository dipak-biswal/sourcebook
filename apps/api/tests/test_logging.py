"""Unit tests for structured JSON logging and request ID middleware."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logging_config import (
    ContextFilter,
    JsonFormatter,
    log_extra,
    request_id_ctx,
    setup_logging,
    user_id_ctx,
)
from app.middleware.request_logging import RequestLoggingMiddleware


def test_json_formatter_includes_core_and_extra_fields():
    setup_logging(level="INFO", json_logs=True)
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "rid-1"  # type: ignore[attr-defined]
    record.event = "http_request"  # type: ignore[attr-defined]
    record.method = "GET"  # type: ignore[attr-defined]
    record.path = "/documents"  # type: ignore[attr-defined]
    record.status_code = 200  # type: ignore[attr-defined]
    record.duration_ms = 12.5  # type: ignore[attr-defined]

    line = JsonFormatter().format(record)
    payload = json.loads(line)

    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert "ts" in payload
    assert payload["request_id"] == "rid-1"
    assert payload["event"] == "http_request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/documents"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5


def test_context_filter_injects_request_and_user_id():
    token_rid = request_id_ctx.set("ctx-rid")
    token_uid = user_id_ctx.set("user-99")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="with context",
            args=(),
            exc_info=None,
        )
        assert ContextFilter().filter(record) is True
        assert record.request_id == "ctx-rid"  # type: ignore[attr-defined]
        assert record.user_id == "user-99"  # type: ignore[attr-defined]
    finally:
        request_id_ctx.reset(token_rid)
        user_id_ctx.reset(token_uid)


def test_log_extra_drops_none():
    assert log_extra(a=1, b=None, c="x") == {"a": 1, "c": "x"}


def _app_with_logging_middleware() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/documents")
    def documents():
        return []

    return app


def test_middleware_generates_and_echoes_request_id():
    client = TestClient(_app_with_logging_middleware())
    response = client.get("/documents")
    assert response.status_code == 200
    rid = response.headers.get("x-request-id")
    assert rid
    assert len(rid) >= 8


def test_middleware_propagates_client_request_id():
    client = TestClient(_app_with_logging_middleware())
    response = client.get("/documents", headers={"X-Request-ID": "manual-corr-1"})
    assert response.headers.get("x-request-id") == "manual-corr-1"


def test_middleware_accepts_correlation_id_header():
    client = TestClient(_app_with_logging_middleware())
    response = client.get(
        "/documents", headers={"X-Correlation-ID": "from-correlation"}
    )
    assert response.headers.get("x-request-id") == "from-correlation"


def test_middleware_skips_access_log_for_health(caplog):
    client = TestClient(_app_with_logging_middleware())
    with caplog.at_level(logging.INFO, logger="sourcebook.http"):
        client.get("/health")
        client.get("/documents")

    request_msgs = [r for r in caplog.records if r.getMessage() == "request"]
    # Only /documents should produce an access log
    assert len(request_msgs) == 1
    assert getattr(request_msgs[0], "path", None) == "/documents"
    assert getattr(request_msgs[0], "event", None) == "http_request"
    assert getattr(request_msgs[0], "status_code", None) == 200
    assert getattr(request_msgs[0], "duration_ms", None) is not None
