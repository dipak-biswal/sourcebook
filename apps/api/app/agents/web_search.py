"""DuckDuckGo web search for agent external context."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_TIME_SENSITIVE = re.compile(
    r"(?i)\b("
    r"requirements?|skills?|trends?|market|salary|salaries|hiring|benchmark|"
    r"expectations?|current|latest|job|role|developer|engineer|full[- ]?stack|ai"
    r")\b"
)
_YEAR = re.compile(r"\b(20\d{2})\b")


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


def search_web(
    query: str,
    *,
    max_results: int = 5,
    region: str = "wt-wt",
    current_year: int | None = None,
) -> dict[str, Any]:
    """
    Run a DuckDuckGo text search.

    Returns a normalized payload for the agent and UI:
    {query, results: [{title, url, snippet}], result_count, error?}
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

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        payload = {
            "query": search_query,
            "results": [],
            "result_count": 0,
            "error": "duckduckgo-search package is not installed",
        }
        if original_query:
            payload["original_query"] = original_query
        return payload

    try:
        raw = DDGS().text(search_query, region=region, max_results=limit)
    except Exception as exc:
        payload = {
            "query": search_query,
            "results": [],
            "result_count": 0,
            "error": str(exc),
        }
        if original_query:
            payload["original_query"] = original_query
        return payload

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
    }
    if original_query:
        payload["original_query"] = original_query
    return payload