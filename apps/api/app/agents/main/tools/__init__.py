"""Main workspace agent tools (search, web, date, notes)."""

from app.agents.main.tools.date import DATE_TOOL_NAMES, current_date_payload, get_current_date
from app.agents.main.tools.fetch_url import fetch_url_content, validate_fetch_url
from app.agents.main.tools.web_search import normalize_web_search_query, search_web


def __getattr__(name: str):
    # Lazy export for build_tools (imports profiles / optional visual tools).
    if name == "build_tools":
        from app.agents.main.tools.factory import build_tools

        return build_tools
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DATE_TOOL_NAMES",
    "build_tools",
    "current_date_payload",
    "fetch_url_content",
    "get_current_date",
    "normalize_web_search_query",
    "search_web",
    "validate_fetch_url",
]
