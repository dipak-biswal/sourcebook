"""Date tools shared by workspace and visual summary agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

DATE_TOOL_NAMES = frozenset({"get_current_date"})


def current_date_payload(*, now: datetime | None = None) -> dict[str, Any]:
    """Return today's date, month, and year in UTC."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    else:
        instant = instant.astimezone(timezone.utc)

    return {
        "date": instant.date().isoformat(),
        "year": instant.year,
        "month": instant.month,
        "month_name": instant.strftime("%B"),
        "timezone": "UTC",
    }


@tool
def get_current_date() -> dict[str, Any]:
    """
    Return today's date, current calendar month, and current year (UTC).
    Call this before time-sensitive web searches or when the user asks about
    "current", "today", or "this year".
    """
    return current_date_payload()


def build_date_tools() -> list:
    """Tools available to any agent profile that lists DATE_TOOL_NAMES."""
    return [get_current_date]