"""Main-agent date-before-tools policy."""

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.tool_policy import (
    format_date_context_message,
    messages_have_date_result,
    prepare_read_tool_calls,
    sort_read_calls_for_execution,
)


def test_messages_have_date_result_from_tool_message():
    messages = [
        ToolMessage(content='{"year": 2026}', tool_call_id="1", name="get_current_date")
    ]
    assert messages_have_date_result(messages) is True


def test_messages_have_date_result_from_seeded_human_message():
    messages = [
        HumanMessage(content=format_date_context_message({"year": 2026, "month_name": "July"}))
    ]
    assert messages_have_date_result(messages) is True


def test_prepare_read_tool_calls_flags_date_before_others():
    read_calls = [
        {"id": "1", "name": "get_current_date", "args": {}},
        {"id": "2", "name": "web_search", "args": {"query": "skills 2026"}},
    ]
    _, calls, sequential = prepare_read_tool_calls(
        read_calls,
        messages=[],
        is_main_agent=True,
    )
    assert calls == read_calls
    assert sequential is True


def test_sort_read_calls_puts_date_first():
    read_calls = [
        {"id": "2", "name": "web_search", "args": {}},
        {"id": "1", "name": "get_current_date", "args": {}},
    ]
    ordered = sort_read_calls_for_execution(read_calls, date_first_sequential=True)
    assert ordered[0]["name"] == "get_current_date"
    assert ordered[1]["name"] == "web_search"


def test_prepare_read_tool_calls_skips_date_when_context_exists():
    messages = [
        HumanMessage(content=format_date_context_message({"year": 2026, "month_name": "July"}))
    ]
    read_calls = [
        {"id": "1", "name": "get_current_date", "args": {}},
        {"id": "2", "name": "list_documents", "args": {}},
    ]
    _, calls, sequential = prepare_read_tool_calls(
        read_calls,
        messages=messages,
        is_main_agent=True,
    )
    assert calls == [{"id": "2", "name": "list_documents", "args": {}}]
    assert sequential is False