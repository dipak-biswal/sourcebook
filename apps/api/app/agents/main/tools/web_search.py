"""Web search for agent/Learn external context.

Primary: Tavily (when TAVILY_API_KEY is set).
Fallback: DuckDuckGo via ``ddgs`` when configured or Tavily is unavailable.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - exercised via ImportError payload
    DDGS = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

_TIME_SENSITIVE = re.compile(
    r"(?i)\b("
    r"requirements?|skills?|trends?|market|salary|salaries|hiring|benchmark|"
    r"expectations?|current|latest|job|role|developer|engineer|full[- ]?stack|ai"
    r")\b"
)
_YEAR = re.compile(r"\b(20\d{2})\b")

_TAVILY_URL = "https://api.tavily.com/search"
# Tavily content is richer than DDG blurbs; allow more for agent grounding.
_SNIPPET_CAP = 1600


def normalize_web_search_query(
    query: str,
    *,
    current_year: int | None = None,
) -> tuple[str, str | None]:
    """
    Bump stale years and add the current year for time-sensitive queries.

    Returns (search_query, original_query) when the query was adjusted.
    """
    q = (query or "").strip()
    if not q:
        return "", None

    year = current_year or datetime.now(timezone.utc).year
    time_sensitive = bool(_TIME_SENSITIVE.search(q))

    def _bump_year(match: re.Match[str]) -> str:
        found = int(match.group(1))
        if time_sensitive and found < year:
            return str(year)
        return match.group(0)

    normalized = _YEAR.sub(_bump_year, q)
    if time_sensitive and not _YEAR.search(normalized):
        normalized = f"{normalized} {year}"

    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized == q:
        return normalized, None
    return normalized, q


def _empty_payload(
    search_query: str,
    *,
    error: str,
    original_query: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": search_query,
        "results": [],
        "result_count": 0,
        "error": error,
    }
    if original_query:
        payload["original_query"] = original_query
    if provider:
        payload["provider"] = provider
    return payload


def _resolve_provider() -> str:
    """Return ``tavily`` or ``ddgs`` based on settings + key presence."""
    raw = (settings.web_search_provider or "auto").strip().lower()
    has_key = bool((settings.tavily_api_key or "").strip())
    if raw == "tavily":
        return "tavily"
    if raw == "ddgs":
        return "ddgs"
    # auto
    return "tavily" if has_key else "ddgs"


def _search_ddgs(
    search_query: str,
    *,
    max_results: int,
    region: str,
    original_query: str | None,
) -> dict[str, Any]:
    if DDGS is None:
        return _empty_payload(
            search_query,
            error="ddgs package is not installed",
            original_query=original_query,
            provider="ddgs",
        )

    try:
        # Explicit timeout — see app/agents/runner/llm.py for why.
        raw = DDGS(timeout=10).text(
            query=search_query,
            region=region,
            max_results=max_results,
            backend="auto",
        )
    except Exception as exc:
        return _empty_payload(
            search_query,
            error=str(exc),
            original_query=original_query,
            provider="ddgs",
        )

    results: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("href") or item.get("url") or "").strip()
        snippet = (item.get("body") or item.get("snippet") or "").strip()
        if not title and not snippet:
            continue
        results.append(
            {
                "title": title or url or "Untitled",
                "url": url,
                "snippet": snippet[:500],
            }
        )

    payload: dict[str, Any] = {
        "query": search_query,
        "results": results,
        "result_count": len(results),
        "provider": "ddgs",
    }
    if original_query:
        payload["original_query"] = original_query
    return payload


def _search_tavily(
    search_query: str,
    *,
    max_results: int,
    original_query: str | None,
) -> dict[str, Any]:
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        return _empty_payload(
            search_query,
            error="TAVILY_API_KEY is not configured",
            original_query=original_query,
            provider="tavily",
        )

    depth = (settings.tavily_search_depth or "basic").strip().lower()
    if depth not in ("basic", "advanced", "fast", "ultra-fast"):
        depth = "basic"

    body = {
        "query": search_query,
        "search_depth": depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_usage": True,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                _TAVILY_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except Exception as exc:
        return _empty_payload(
            search_query,
            error=f"Tavily request failed: {exc}",
            original_query=original_query,
            provider="tavily",
        )

    if resp.status_code == 401:
        return _empty_payload(
            search_query,
            error="Tavily unauthorized: check TAVILY_API_KEY",
            original_query=original_query,
            provider="tavily",
        )
    if resp.status_code == 429:
        return _empty_payload(
            search_query,
            error="Tavily rate limited",
            original_query=original_query,
            provider="tavily",
        )
    if resp.status_code in (432, 433):
        return _empty_payload(
            search_query,
            error="Tavily credit/plan limit exceeded",
            original_query=original_query,
            provider="tavily",
        )
    if resp.status_code >= 400:
        detail = ""
        try:
            data = resp.json()
            if isinstance(data, dict):
                err = data.get("detail") or data.get("error") or data
                detail = str(err)[:200]
        except Exception:
            detail = (resp.text or "")[:200]
        return _empty_payload(
            search_query,
            error=f"Tavily HTTP {resp.status_code}"
            + (f": {detail}" if detail else ""),
            original_query=original_query,
            provider="tavily",
        )

    try:
        data = resp.json()
    except Exception:
        return _empty_payload(
            search_query,
            error="Tavily returned invalid JSON",
            original_query=original_query,
            provider="tavily",
        )

    if not isinstance(data, dict):
        return _empty_payload(
            search_query,
            error="Tavily returned unexpected payload",
            original_query=original_query,
            provider="tavily",
        )

    results: list[dict[str, str]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or item.get("snippet") or "").strip()
        if not title and not content:
            continue
        results.append(
            {
                "title": title or url or "Untitled",
                "url": url,
                "snippet": content[:_SNIPPET_CAP],
            }
        )

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    credits = usage.get("credits")
    logger.info(
        "web_search provider=tavily depth=%s results=%s credits=%s",
        depth,
        len(results),
        credits,
    )

    payload: dict[str, Any] = {
        "query": search_query,
        "results": results,
        "result_count": len(results),
        "provider": "tavily",
    }
    if original_query:
        payload["original_query"] = original_query
    if credits is not None:
        payload["credits_used"] = credits
    return payload


def _should_fallback_to_ddgs(tavily_out: dict[str, Any]) -> bool:
    if not settings.tavily_fallback_to_ddgs:
        return False
    err = str(tavily_out.get("error") or "").lower()
    if not err:
        # Empty results without error: still allow fallback for resilience.
        return int(tavily_out.get("result_count") or 0) == 0
    # Do not fallback on missing key when user forced tavily-only path handled elsewhere.
    fallback_markers = (
        "rate limited",
        "credit",
        "plan limit",
        "request failed",
        "http 5",
        "unauthorized",
        "invalid json",
        "unexpected payload",
    )
    return any(m in err for m in fallback_markers) or "http " in err


def search_web(
    query: str,
    *,
    max_results: int = 5,
    region: str = "us-en",
    current_year: int | None = None,
) -> dict[str, Any]:
    """
    Run a web search (Tavily when configured, else DuckDuckGo).

    Returns a normalized payload for the agent and UI:
    {query, results: [{title, url, snippet}], result_count, error?, provider?}
    """
    q = (query or "").strip()
    if not q:
        return {
            "query": "",
            "results": [],
            "result_count": 0,
            "error": "Query is required",
        }

    limit = max(1, min(int(max_results), 8))
    search_query, original_query = normalize_web_search_query(
        q, current_year=current_year
    )
    provider = _resolve_provider()

    if provider == "tavily":
        out = _search_tavily(
            search_query,
            max_results=limit,
            original_query=original_query,
        )
        if out.get("error") or out.get("result_count") == 0:
            if (
                (settings.web_search_provider or "auto").strip().lower() != "tavily"
                and _should_fallback_to_ddgs(out)
            ):
                logger.warning(
                    "web_search tavily failed (%s); falling back to ddgs",
                    out.get("error") or "no results",
                )
                fb = _search_ddgs(
                    search_query,
                    max_results=limit,
                    region=region,
                    original_query=original_query,
                )
                if not fb.get("error"):
                    fb["provider"] = "ddgs"
                    fb["fallback_from"] = "tavily"
                    if out.get("error"):
                        fb["tavily_error"] = out["error"]
                    return fb
                # Prefer original Tavily error if both failed.
                if out.get("error"):
                    return out
                return fb
        return out

    return _search_ddgs(
        search_query,
        max_results=limit,
        region=region,
        original_query=original_query,
    )
