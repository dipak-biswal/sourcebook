"""LangChain message (de)serialization and small message helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def _content_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _hash_args(name: str, args: dict[str, Any]) -> str:
    """Deterministic hash of a (tool_name, args) pair for duplicate detection."""
    raw = json.dumps([name, args], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": _content_str(m.content)})
        elif isinstance(m, HumanMessage):
            out.append({"role": "human", "content": _content_str(m.content)})
        elif isinstance(m, AIMessage):
            item: dict[str, Any] = {
                "role": "ai",
                "content": _content_str(m.content),
            }
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.get("id"),
                        "name": tc.get("name"),
                        "args": tc.get("args") or {},
                        "type": tc.get("type") or "tool_call",
                    }
                    for tc in m.tool_calls
                ]
            out.append(item)
        elif isinstance(m, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "content": _content_str(m.content),
                    "tool_call_id": m.tool_call_id,
                    "name": getattr(m, "name", None) or "",
                }
            )
    return out


def _deserialize_messages(raw: list[Any]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role == "system":
            messages.append(SystemMessage(content=str(item.get("content") or "")))
        elif role == "human":
            messages.append(HumanMessage(content=str(item.get("content") or "")))
        elif role == "ai":
            tool_calls = item.get("tool_calls") or []
            messages.append(
                AIMessage(
                    content=str(item.get("content") or ""),
                    tool_calls=tool_calls,
                )
            )
        elif role == "tool":
            messages.append(
                ToolMessage(
                    content=str(item.get("content") or ""),
                    tool_call_id=str(item.get("tool_call_id") or str(uuid.uuid4())),
                    name=str(item.get("name") or ""),
                )
            )
    return messages
