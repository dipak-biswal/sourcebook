"""LLM client construction, streaming turns, and token accounting."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.agents.execution_trace import LiveTraceContext
from app.agents.runner.events import EventCallback, _emit
from app.agents.runner.messages import _content_str, _serialize_messages
from app.config import settings
from app.models import AgentRun
from app.usage import estimate_tokens, log_usage


def _llm(model: str | None = None):
    return ChatOpenAI(
        model=model or settings.chat_model,
        api_key=SecretStr(settings.openai_api_key),
        base_url=settings.openai_base_url,
        temperature=0.1,
        stream_usage=True,
        # Explicit bounds so a stalled connection fails fast with a catchable
        # error instead of relying on library defaults (which can be absent
        # or vary between versions) — a run should never hang indefinitely.
        timeout=90.0,
        max_retries=2,
    )


def _invoke_llm_turn(
    model: Any,
    messages: list[BaseMessage],
    *,
    on_event: EventCallback,
    run_id: uuid.UUID,
    turn_id: str,
    trace_live: LiveTraceContext | None = None,
    on_trace: Callable[[], None] | None = None,
) -> tuple[AIMessage, float]:
    """Stream one LLM turn; emit llm_delta chunks for live trace UI."""
    t0 = time.perf_counter()
    gathered: AIMessage | None = None
    for chunk in model.stream(messages):
        gathered = chunk if gathered is None else gathered + chunk  # type: ignore[operator,assignment]
        delta = _content_str(getattr(chunk, "content", None))
        if delta:
            if trace_live is not None:
                trace_live.stream_by_turn[turn_id] = (
                    trace_live.stream_by_turn.get(turn_id, "") + delta
                )
            _emit(
                on_event,
                "llm_delta",
                run_id=str(run_id),
                turn_id=turn_id,
                delta=delta,
            )
            if on_trace:
                on_trace()
    if gathered is None:
        gathered = AIMessage(content="")
    llm_ms = (time.perf_counter() - t0) * 1000
    return gathered, llm_ms


def _tokens_from_ai_message(ai: AIMessage) -> tuple[int, int, int]:
    meta = getattr(ai, "usage_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        prompt = int(meta.get("input_tokens") or meta.get("prompt_tokens") or 0)
        completion = int(
            meta.get("output_tokens") or meta.get("completion_tokens") or 0
        )
        total = int(meta.get("total_tokens") or (prompt + completion) or 0)
        if total > 0:
            return prompt, completion, total

    resp = getattr(ai, "response_metadata", None) or {}
    usage = resp.get("token_usage") or resp.get("usage") or {}
    if isinstance(usage, dict) and usage:
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total = int(usage.get("total_tokens") or (prompt + completion) or 0)
        if total > 0:
            return prompt, completion, total

    return _estimate_turn_tokens([], ai)


def _estimate_turn_tokens(
    messages: list[BaseMessage],
    ai: AIMessage,
) -> tuple[int, int, int]:
    """Split token estimate into prompt vs completion when provider omits usage."""
    prompt_est = estimate_tokens(
        json.dumps(_serialize_messages(messages), default=str),
    )
    completion_parts = [_content_str(ai.content)]
    for tc in ai.tool_calls or []:
        completion_parts.append(str(tc.get("name") or ""))
        completion_parts.append(json.dumps(tc.get("args") or {}, default=str))
    completion_est = estimate_tokens(*completion_parts)
    total = prompt_est + completion_est
    return prompt_est, completion_est, max(total, 1)


def _tokens_for_turn(
    messages: list[BaseMessage],
    ai: AIMessage,
) -> tuple[int, int, int]:
    p, c, t = _tokens_from_ai_message(ai)
    if p > 0 or c > 0:
        return p, c, t if t > 0 else p + c
    if t > 0:
        return _estimate_turn_tokens(messages, ai)
    return _estimate_turn_tokens(messages, ai)


def _log_agent_usage(
    db: Session,
    run: AgentRun,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return
    log_usage(
        db,
        kind="agent_run",
        model=settings.chat_model,
        user_id=run.user_id,
        workspace_id=run.workspace_id,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
        meta={"run_id": str(run.id), "status": run.status},
    )
