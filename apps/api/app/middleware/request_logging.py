"""Request ID + structured access logs."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import get_logger, log_extra, request_id_ctx, user_id_ctx

logger = get_logger("sourcebook.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id") or request.headers.get(
            "x-correlation-id"
        )
        request_id = incoming.strip() if incoming else str(uuid.uuid4())
        token_rid = request_id_ctx.set(request_id)
        token_uid = user_id_ctx.set(None)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "unhandled_error",
                extra=log_extra(
                    event="http_error",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                ),
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # Skip noisy health checks at debug would be nicer; log at info for portfolio demos
            if request.url.path not in ("/health", "/docs", "/openapi.json", "/redoc"):
                logger.info(
                    "request",
                    extra=log_extra(
                        event="http_request",
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                    ),
                )
            request_id_ctx.reset(token_rid)
            user_id_ctx.reset(token_uid)
