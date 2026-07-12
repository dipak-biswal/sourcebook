"""Per-user fixed-window rate limits (Redis, with in-memory fallback)."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict

from fastapi import Depends, HTTPException, status

from app.config import settings
from app.deps import get_current_user
from app.models import User

# --- in-memory fallback (single API process only) ---
_lock = threading.Lock()
_memory: dict[str, list[float]] = defaultdict(list)


def _memory_allow(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = time.time()
    with _lock:
        hits = [t for t in _memory[key] if now - t < window_seconds]
        if len(hits) >= limit:
            _memory[key] = hits
            retry = int(window_seconds - (now - hits[0])) if hits else window_seconds
            return False, max(1, retry)
        hits.append(now)
        _memory[key] = hits
        return True, 0


def _redis_allow(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    from redis import Redis

    r = Redis.from_url(settings.redis_url)
    # Fixed window: key expires after window
    count = r.incr(key)
    if count == 1:
        r.expire(key, window_seconds)
    if count > limit:
        ttl = r.ttl(key)
        retry = int(ttl) if ttl and ttl > 0 else window_seconds
        return False, retry
    return True, 0


def check_rate_limit(
    *,
    user_id: uuid.UUID,
    scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Raise HTTP 429 if the user exceeds limit for scope in the window."""
    if not settings.rate_limit_enabled or limit <= 0:
        return

    window_id = int(time.time() // window_seconds)
    key = f"rl:{scope}:{user_id}:{window_id}"

    try:
        allowed, retry_after = _redis_allow(key, limit, window_seconds)
    except Exception:
        # Redis down → process-local limiter
        allowed, retry_after = _memory_allow(key, limit, window_seconds)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded for '{scope}' "
                f"({limit} requests per {window_seconds}s). "
                f"Retry after ~{retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit(scope: str, limit: int | None = None, window_seconds: int | None = None):
    """
    FastAPI dependency factory.

    Usage:
        current_user: User = Depends(get_current_user),
        _: None = Depends(rate_limit("chat")),
    """

    def _dep(current_user: User = Depends(get_current_user)) -> None:
        lim = limit
        win = window_seconds or settings.rate_limit_window_seconds
        if lim is None:
            if scope == "chat":
                lim = settings.rate_limit_chat_per_window
            elif scope == "ingest":
                lim = settings.rate_limit_ingest_per_window
            elif scope == "agent":
                lim = settings.rate_limit_agent_per_window
            else:
                lim = settings.rate_limit_chat_per_window
        check_rate_limit(
            user_id=current_user.id,
            scope=scope,
            limit=lim,
            window_seconds=win,
        )

    return _dep
