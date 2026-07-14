"""DuckDuckGo web search for agent external context."""

from __future__ import annotations

from typing import Any


def search_web(
    query: str,
    *,
    max_results: int = 5,
    region: str = "wt-wt",
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

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {
            "query": q,
            "results": [],
            "result_count": 0,
            "error": "duckduckgo-search package is not installed",
        }

    try:
        raw = DDGS().text(q, region=region, max_results=limit)
    except Exception as exc:
        return {
            "query": q,
            "results": [],
            "result_count": 0,
            "error": str(exc),
        }

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

    return {
        "query": q,
        "results": results,
        "result_count": len(results),
    }