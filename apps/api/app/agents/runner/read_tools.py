"""Parallel read-tool execution with date-first policy and auto-seeding."""

from __future__ import annotations

import concurrent.futures
import json
import time
import uuid
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from sqlalchemy.orm import Session

from app.agents.runner.events import EventCallback, _append_step, _emit
from app.visual_summary.pipeline import (
    _accumulate_visual_tool_tokens,
    _apply_render_ui_result,
    _visual_tool_result_input,
)
from app.agents.tool_policy import (
    DATE_TOOL_NAME,
    format_date_context_message,
    messages_have_date_result,
    prepare_read_tool_calls,
    sort_read_calls_for_execution,
)
from app.models import AgentRun
from app.visual_summary.context import PresentationContext


def _is_main_agent_loop(*, finalize_mode: str, agent_type_override: str | None) -> bool:
    return finalize_mode == "main" and (agent_type_override or "general") == "general"


def _auto_seed_current_date(
    db: Session,
    run: AgentRun,
    *,
    messages: list[BaseMessage],
    tool_by_name: dict[str, Any],
    step_index: int,
    on_event: EventCallback,
) -> tuple[list[BaseMessage], int]:
    """Run get_current_date once and inject context before other read tools."""
    if messages_have_date_result(messages):
        return messages, step_index
    tool = tool_by_name.get(DATE_TOOL_NAME)
    if not tool:
        return messages, step_index

    t0 = time.perf_counter()
    try:
        result = tool.invoke({})
    except Exception as e:
        result = {"error": str(e)}
    ms = (time.perf_counter() - t0) * 1000

    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_call",
        tool_name=DATE_TOOL_NAME,
        input={"auto_seeded": True},
        on_event=on_event,
    )
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_result",
        tool_name=DATE_TOOL_NAME,
        input={"auto_seeded": True},
        output=result,
        on_event=on_event,
        duration_ms=round(ms, 1),
    )
    _emit(
        on_event,
        "tool_start",
        run_id=str(run.id),
        tool_name=DATE_TOOL_NAME,
        tool_args={},
        call_id="auto-date",
    )

    out = list(messages)
    out.append(HumanMessage(content=format_date_context_message(result)))
    return out, step_index


def _run_read_tool_batch(
    read_calls: list[dict[str, Any]],
    *,
    tool_by_name: dict[str, Any],
    date_first_sequential: bool,
) -> list[dict[str, Any]]:
    ordered = sort_read_calls_for_execution(
        read_calls,
        date_first_sequential=date_first_sequential,
    )

    def _run_one(tc: dict) -> dict[str, Any]:
        name = tc.get("name") or ""
        args = tc.get("args") or {}
        call_id = tc.get("id") or str(uuid.uuid4())
        tool = tool_by_name.get(name)
        t0 = time.perf_counter()
        if not tool:
            result: Any = {"error": f"Unknown tool: {name}"}
        else:
            try:
                result = tool.invoke(args)
            except Exception as e:
                result = {"error": str(e)}
        ms = (time.perf_counter() - t0) * 1000
        return {"call_id": call_id, "name": name, "args": args, "result": result, "ms": ms}

    if date_first_sequential and len(ordered) > 1:
        date_calls = [tc for tc in ordered if tc.get("name") == DATE_TOOL_NAME]
        other_calls = [tc for tc in ordered if tc.get("name") != DATE_TOOL_NAME]
        results = [_run_one(tc) for tc in date_calls]
        if other_calls:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results.extend(pool.map(_run_one, other_calls))
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(_run_one, ordered))


def _apply_read_tool_results(
    db: Session,
    run: AgentRun,
    *,
    results: list[dict[str, Any]],
    messages: list[BaseMessage],
    step_index: int,
    on_event: EventCallback,
    finalize_mode: str,
    presentation_context: PresentationContext | None,
    prompt_tokens_total: int,
    completion_tokens_total: int,
    total_tokens_acc: int,
) -> tuple[list[BaseMessage], int, int, int, int]:
    for r in results:
        step_index += 1
        _append_step(
            db,
            run,
            step_index=step_index,
            type="tool_result",
            tool_name=r["name"],
            input=_visual_tool_result_input(
                r["name"],
                r["args"],
                r["result"],
            ),
            output=r["result"],
            on_event=on_event,
            duration_ms=round(r["ms"], 1),
        )
        if finalize_mode == "visual_summary":
            prompt_tokens_total, completion_tokens_total, total_tokens_acc = (
                _accumulate_visual_tool_tokens(
                    r["result"],
                    prompt_tokens_total=prompt_tokens_total,
                    completion_tokens_total=completion_tokens_total,
                    total_tokens_acc=total_tokens_acc,
                )
            )
            _apply_render_ui_result(
                run,
                tool_name=r["name"],
                result=r["result"],
                on_event=on_event,
            )
        messages.append(
            ToolMessage(
                content=json.dumps(r["result"], default=str),
                tool_call_id=r["call_id"],
                name=r["name"],
            )
        )
    return (
        messages,
        step_index,
        prompt_tokens_total,
        completion_tokens_total,
        total_tokens_acc,
    )


def _process_read_tool_calls(
    db: Session,
    run: AgentRun,
    *,
    read_calls: list[dict[str, Any]],
    messages: list[BaseMessage],
    step_index: int,
    tool_by_name: dict[str, Any],
    on_event: EventCallback,
    finalize_mode: str,
    agent_type_override: str | None,
    presentation_context: PresentationContext | None,
    prompt_tokens_total: int,
    completion_tokens_total: int,
    total_tokens_acc: int,
    emit_parallel_group: bool,
) -> tuple[list[BaseMessage], int, int, int, int]:
    if not read_calls:
        return (
            messages,
            step_index,
            prompt_tokens_total,
            completion_tokens_total,
            total_tokens_acc,
        )

    is_main = _is_main_agent_loop(
        finalize_mode=finalize_mode,
        agent_type_override=agent_type_override,
    )
    messages, read_calls, date_first = prepare_read_tool_calls(
        read_calls,
        messages=messages,
        is_main_agent=is_main,
    )
    if is_main and any(tc.get("name") != DATE_TOOL_NAME for tc in read_calls):
        model_requested_date = any(
            tc.get("name") == DATE_TOOL_NAME for tc in read_calls
        )
        if not messages_have_date_result(messages) and not model_requested_date:
            messages, step_index = _auto_seed_current_date(
                db,
                run,
                messages=messages,
                tool_by_name=tool_by_name,
                step_index=step_index,
                on_event=on_event,
            )
        messages, read_calls, date_first = prepare_read_tool_calls(
            read_calls,
            messages=messages,
            is_main_agent=is_main,
        )

    if emit_parallel_group:
        _emit(
            on_event,
            "parallel_group",
            run_id=str(run.id),
            tool_names=[tc.get("name") for tc in read_calls],
            count=len(read_calls),
        )

    read_results = _run_read_tool_batch(
        read_calls,
        tool_by_name=tool_by_name,
        date_first_sequential=date_first,
    )
    return _apply_read_tool_results(
        db,
        run,
        results=read_results,
        messages=messages,
        step_index=step_index,
        on_event=on_event,
        finalize_mode=finalize_mode,
        presentation_context=presentation_context,
        prompt_tokens_total=prompt_tokens_total,
        completion_tokens_total=completion_tokens_total,
        total_tokens_acc=total_tokens_acc,
    )
