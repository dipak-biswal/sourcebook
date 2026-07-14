from datetime import datetime, timezone

from app.agents.date_tools import current_date_payload, get_current_date


def test_current_date_payload_returns_month_and_year():
    payload = current_date_payload(
        now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
    )
    assert payload["date"] == "2026-07-14"
    assert payload["year"] == 2026
    assert payload["month"] == 7
    assert payload["month_name"] == "July"
    assert payload["timezone"] == "UTC"


def test_get_current_date_tool_invokes():
    result = get_current_date.invoke({})
    assert isinstance(result["year"], int)
    assert isinstance(result["month"], int)
    assert isinstance(result["month_name"], str)
    assert result["timezone"] == "UTC"