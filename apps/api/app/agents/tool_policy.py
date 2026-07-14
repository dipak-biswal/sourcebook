"""Tool ordering and date-context policy for the main workspace agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

DATE_TOOL_NAME = "get_current_date"

GENERAL_TOOL_ORDER: tuple[str, ...] = (
    "get_current_date",
    "list_documents",
    "search_documents",
    "web_search",
    "create_note",
)


def messages_have_date_result(messages: list[BaseMessage]) -> bool:
    marker = "CURRENT DATE CONTEXT (from get_current_date"
    for message in messages:
        if isinstance(message, ToolMessage) and (message.name or "") == DATE_TOOL_NAME:
            return True
        if isinstance(message, HumanMessage):
            content = (
                message.content
                if isinstance(message.content, str)
                else str(message.content or "")
            )
            if marker in content:
                return True
    return False


def format_date_context_message(result: dict[str, Any]) -> str:
    return (
        "CURRENT DATE CONTEXT (from get_current_date — use for web_search queries "
        "and any time-sensitive comparisons in this run):\n"
        f"{json.dumps(result, ensure_ascii=False)}\n"
        f"Today is {result.get('month_name')} {result.get('year')} (UTC)."
    )


def prepare_read_tool_calls(
    read_calls: list[dict[str, Any]],
    *,
    messages: list[BaseMessage],
    is_main_agent: bool,
) -> tuple[list[BaseMessage], list[dict[str, Any]], bool]:
    """
    Ensure the main agent has current-date context before other read tools.

    Returns (messages, calls_to_run, run_date_before_others_sequentially).
    """
    if not is_main_agent or not read_calls:
        return messages, read_calls, False

    has_date = messages_have_date_result(messages)
    date_calls = [tc for tc in read_calls if tc.get("name") == DATE_TOOL_NAME]
    other_calls = [tc for tc in read_calls if tc.get("name") != DATE_TOOL_NAME]

    updated_messages = list(messages)
    if other_calls and not has_date and not date_calls:
        # Caller must invoke get_current_date and append HumanMessage before executing.
        return updated_messages, read_calls, False

    if date_calls and other_calls:
        # Satisfy date tool_call first; other tools run after date ToolMessage exists.
        return updated_messages, read_calls, True

    return updated_messages, read_calls, False


def sort_read_calls_for_execution(
    read_calls: list[dict[str, Any]],
    *,
    date_first_sequential: bool,
) -> list[dict[str, Any]]:
    if not date_first_sequential:
        return read_calls
    date_calls = [tc for tc in read_calls if tc.get("name") == DATE_TOOL_NAME]
    other_calls = [tc for tc in read_calls if tc.get("name") != DATE_TOOL_NAME]
    return date_calls + other_calls