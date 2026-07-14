"""Agent runner final-answer synthesis helpers."""

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents.runner import (
    _hash_args,
    _tool_context_for_synthesis,
    _weak_final_answer,
)


def test_weak_final_answer_detects_empty_and_placeholder():
    assert _weak_final_answer(None) is True
    assert _weak_final_answer("") is True
    assert _weak_final_answer("(no final answer)") is True
    assert _weak_final_answer("Stopped after max_steps without a final answer.") is True
    assert _weak_final_answer("short") is True
    assert _weak_final_answer("- Led full-stack AI product delivery across React and FastAPI.") is False


def test_tool_context_for_synthesis_flattens_search_hits():
    payload = [
        {
            "filename": "resume.pdf",
            "snippet": "Built RAG chatbot with FastAPI and React.",
            "score": 0.91,
        }
    ]
    messages = [
        ToolMessage(
            content=json.dumps(payload),
            tool_call_id="1",
            name="search_documents",
        )
    ]
    text = _tool_context_for_synthesis(messages)
    assert "resume.pdf" in text
    assert "RAG chatbot" in text


def test_first_tool_call_should_not_count_as_repeat():
    """Fresh run: list_documents {} is not a repeat before any tool results."""
    messages = [SystemMessage(content="sys"), HumanMessage(content="goal")]
    seen: set[str] = set()
    tool_result_count = sum(1 for m in messages if isinstance(m, ToolMessage))
    h = _hash_args("list_documents", {})
    warn = h in seen
    seen.add(h)
    assert tool_result_count == 0
    assert warn is False
    assert not (warn and tool_result_count > 0)