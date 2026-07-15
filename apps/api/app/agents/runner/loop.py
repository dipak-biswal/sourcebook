"""The shared LLM ↔ tools loop used by both the main and visual agents."""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import BaseMessage, ToolMessage
from sqlalchemy.orm import Session

from app.agents.execution_trace import LiveTraceContext
from app.agents.runner.constants import WRITE_TOOLS
from app.agents.runner.events import (
    EventCallback,
    _append_step,
    _emit,
    _next_step_index,
    _refresh_execution_trace,
)
from app.agents.runner.finalize import _finalize_completed_run
from app.agents.runner.llm import (
    _invoke_llm_turn,
    _llm,
    _log_agent_usage,
    _tokens_for_turn,
)
from app.agents.runner.messages import _content_str, _hash_args, _serialize_messages
from app.agents.runner.read_tools import _process_read_tool_calls
from app.agents.runner.visual import (
    _finalize_visual_summary_run,
    _visual_tool_call_input,
)
from app.agents.tools import build_tools
from app.config import settings
from app.models import AgentRun
from app.presentation.context import PresentationContext


def _run_tool_loop(
    db: Session,
    run: AgentRun,
    *,
    messages: list[BaseMessage],
    max_steps: int,
    prompt_tokens_total: int = 0,
    completion_tokens_total: int = 0,
    total_tokens_acc: int = 0,
    start_step_index: int | None = None,
    on_event: EventCallback = None,
    trace_live: LiveTraceContext | None = None,
    agent_type_override: str | None = None,
    presentation_context: PresentationContext | None = None,
    chat_model: str | None = None,
    finalize_mode: str = "main",
    initial_token_usage: int = 0,
) -> AgentRun:
    """
    Shared LLM ↔ tools loop.

    Pauses on first write tool with a checkpoint in pending_tool so approve can resume.
    """
    user_id = run.user_id or uuid.UUID(int=0)
    resolved_agent_type = agent_type_override or run.agent_type
    resolved_model = chat_model or settings.chat_model
    tools = build_tools(
        db,
        workspace_id=run.workspace_id,
        user_id=user_id,
        agent_type=resolved_agent_type,
        presentation_context=presentation_context,
    )
    tool_by_name = {t.name: t for t in tools}
    model = _llm(resolved_model).bind_tools(tools)

    step_index = (
        start_step_index
        if start_step_index is not None
        else max(0, _next_step_index(db, run.id) - 1)
    )
    seen_calls: set[str] = set()
    if trace_live is None:
        trace_live = LiveTraceContext()
    run._trace_live = trace_live  # type: ignore[attr-defined]

    def refresh_trace() -> None:
        _refresh_execution_trace(db, run, on_event, trace_live)

    def finish_run(step_index: int, *, fallback_answer: str) -> int:
        run.status = "completed"
        combined_usage = initial_token_usage + total_tokens_acc
        run.token_usage = combined_usage or None
        run.pending_tool = None
        if finalize_mode == "visual_summary":
            return _finalize_visual_summary_run(
                db,
                run,
                step_index=step_index,
                on_event=on_event,
            )
        return _finalize_completed_run(
            db,
            run,
            messages=messages,
            fallback_answer=fallback_answer,
            step_index=step_index,
            on_event=on_event,
        )

    try:
        for _ in range(max(1, max_steps)):
            turn_id = str(uuid.uuid4())
            trace_live.current_turn_id = turn_id
            trace_live.llm_running = True
            trace_live.has_tool_calls = False
            trace_live.prompt_by_turn[turn_id] = _serialize_messages(messages)
            trace_live.tokens_by_turn.pop(turn_id, None)
            trace_live.model_by_turn[turn_id] = resolved_model
            _emit(
                on_event,
                "llm_start",
                run_id=str(run.id),
                turn_id=turn_id,
                name="ChatOpenAI",
                model=resolved_model,
                status=run.status,
            )
            refresh_trace()
            ai, llm_ms = _invoke_llm_turn(
                model,
                messages,
                on_event=on_event,
                run_id=run.id,
                turn_id=turn_id,
                trace_live=trace_live,
                on_trace=refresh_trace,
            )

            p, c, t = _tokens_for_turn(messages, ai)
            prompt_tokens_total += p
            completion_tokens_total += c
            total_tokens_acc += t if t else (p + c)
            _emit(
                on_event,
                "llm_end",
                run_id=str(run.id),
                turn_id=turn_id,
                name="ChatOpenAI",
                model=resolved_model,
                duration_ms=round(llm_ms, 1),
                prompt_tokens=p,
                completion_tokens=c,
                total_tokens=t if t else (p + c),
                has_tool_calls=bool(ai.tool_calls),
                token_usage_so_far=total_tokens_acc,
            )
            trace_live.llm_running = False
            trace_live.has_tool_calls = bool(ai.tool_calls)
            trace_live.tokens_by_turn[turn_id] = {
                "prompt_tokens": p,
                "completion_tokens": c,
                "total_tokens": t if t else (p + c),
            }
            refresh_trace()

            # Duplicate detection — check BEFORE appending ai so we don't
            # orphan tool_calls without ToolMessage responses.
            if ai.tool_calls:
                warn_about_loop = False
                for tc in ai.tool_calls:
                    h = _hash_args(tc.get("name") or "", tc.get("args") or {})
                    if h in seen_calls:
                        warn_about_loop = True
                    seen_calls.add(h)

                tool_result_count = sum(
                    1 for m in messages if isinstance(m, ToolMessage)
                )
                # Never abort before at least one tool round — avoids false positives
                # from duplicate hashes across runs/threads or twin calls in one turn.
                if warn_about_loop and tool_result_count > 0:
                    _emit(
                        on_event,
                        "loop_warning",
                        run_id=str(run.id),
                        message="Agent is repeating the same tool call — breaking loop",
                    )
                    # Don't append ai (would orphan tool_calls), don't re-invoke LLM.
                    # Just exit — repeated calls waste tokens.
                    step_index = finish_run(
                        step_index,
                        fallback_answer=_content_str(ai.content) or "(no final answer)",
                    )
                    _log_agent_usage(
                        db,
                        run,
                        prompt_tokens=prompt_tokens_total,
                        completion_tokens=completion_tokens_total,
                        total_tokens=total_tokens_acc,
                    )
                    db.commit()
                    db.refresh(run)
                    _emit(
                        on_event,
                        "status",
                        run_id=str(run.id),
                        status=run.status,
                        token_usage=run.token_usage,
                        pending_tool=run.pending_tool,
                        final_answer=run.final_answer,
                    )
                    return run

            prompt_messages = _serialize_messages(messages)
            messages.append(ai)

            if ai.tool_calls:
                for tc in ai.tool_calls:
                    step_index += 1
                    _append_step(
                        db,
                        run,
                        step_index=step_index,
                        type="tool_call",
                        tool_name=tc.get("name"),
                        input=_visual_tool_call_input(
                            str(tc.get("name") or ""),
                            tc.get("args"),
                            ctx=presentation_context,
                        ),
                        on_event=on_event,
                    )
            content = _content_str(ai.content)
            if content:
                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="thought" if ai.tool_calls else "final",
                    input={
                        "messages": prompt_messages,
                        "model": resolved_model,
                        "prompt_tokens": p,
                        "completion_tokens": c,
                        "total_tokens": t if t else (p + c),
                    },
                    output=content,
                    on_event=on_event,
                    duration_ms=llm_ms if not ai.tool_calls else None,
                )

            if not ai.tool_calls:
                step_index = finish_run(
                    step_index,
                    fallback_answer=content or "(no final answer)",
                )
                _log_agent_usage(
                    db,
                    run,
                    prompt_tokens=prompt_tokens_total,
                    completion_tokens=completion_tokens_total,
                    total_tokens=total_tokens_acc,
                )
                db.commit()
                db.refresh(run)
                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status=run.status,
                    token_usage=run.token_usage,
                    pending_tool=run.pending_tool,
                    final_answer=run.final_answer,
                )
                return run

            write_calls = [
                tc for tc in ai.tool_calls if tc.get("name") in WRITE_TOOLS
            ]
            if write_calls:
                tc = write_calls[0]
                # Execute non-write tools from the same turn in parallel first
                read_before_write = [
                    rtc for rtc in ai.tool_calls if rtc.get("name") not in WRITE_TOOLS
                ]
                if read_before_write:
                    for rtc in read_before_write:
                        _emit(
                            on_event,
                            "tool_start",
                            run_id=str(run.id),
                            tool_name=rtc.get("name"),
                            tool_args=rtc.get("args"),
                            call_id=rtc.get("id"),
                        )
                    (
                        messages,
                        step_index,
                        prompt_tokens_total,
                        completion_tokens_total,
                        total_tokens_acc,
                    ) = _process_read_tool_calls(
                        db,
                        run,
                        read_calls=read_before_write,
                        messages=messages,
                        step_index=step_index,
                        tool_by_name=tool_by_name,
                        on_event=on_event,
                        finalize_mode=finalize_mode,
                        agent_type_override=agent_type_override,
                        presentation_context=presentation_context,
                        prompt_tokens_total=prompt_tokens_total,
                        completion_tokens_total=completion_tokens_total,
                        total_tokens_acc=total_tokens_acc,
                        emit_parallel_group=True,
                    )

                run.status = "waiting_approval"
                run.pending_tool = {
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                    # Checkpoint for resume-after-approve
                    "checkpoint": {
                        "messages": _serialize_messages(messages),
                        "max_steps": max_steps,
                        "prompt_tokens": prompt_tokens_total,
                        "completion_tokens": completion_tokens_total,
                        "total_tokens": total_tokens_acc,
                    },
                }
                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="approval",
                    tool_name=tc.get("name"),
                    input=tc.get("args") or {},
                    output={
                        "status": "waiting_approval",
                        "resumable": True,
                    },
                    on_event=on_event,
                )
                run.token_usage = total_tokens_acc or None
                run.final_answer = (
                    "Waiting for your approval to run "
                    f"`{tc.get('name')}` with args: {json.dumps(tc.get('args') or {})}. "
                    "After you approve, the agent will continue."
                )
                # Don't log completion usage yet — resume will log final
                db.commit()
                db.refresh(run)
                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status=run.status,
                    token_usage=run.token_usage,
                    pending_tool=run.pending_tool,
                    final_answer=run.final_answer,
                )
                return run

            # Emit tool_start events for every tool call in this turn
            for tc in ai.tool_calls:
                name = tc.get("name")
                if name and name not in trace_live.running_tool_names:
                    trace_live.running_tool_names.append(str(name))
                _emit(
                    on_event,
                    "tool_start",
                    run_id=str(run.id),
                    tool_name=name,
                    tool_args=tc.get("args"),
                    call_id=tc.get("id"),
                )
            if ai.tool_calls:
                refresh_trace()

            # Execute read tools in parallel
            read_calls = [
                tc for tc in ai.tool_calls if tc.get("name") not in WRITE_TOOLS
            ]

            if read_calls:
                (
                    messages,
                    step_index,
                    prompt_tokens_total,
                    completion_tokens_total,
                    total_tokens_acc,
                ) = _process_read_tool_calls(
                    db,
                    run,
                    read_calls=read_calls,
                    messages=messages,
                    step_index=step_index,
                    tool_by_name=tool_by_name,
                    on_event=on_event,
                    finalize_mode=finalize_mode,
                    agent_type_override=agent_type_override,
                    presentation_context=presentation_context,
                    prompt_tokens_total=prompt_tokens_total,
                    completion_tokens_total=completion_tokens_total,
                    total_tokens_acc=total_tokens_acc,
                    emit_parallel_group=True,
                )
                trace_live.running_tool_names = []
                refresh_trace()

        step_index = finish_run(
            step_index,
            fallback_answer=(
                run.final_answer or "Stopped after max_steps without a final answer."
            ),
        )
        _log_agent_usage(
            db,
            run,
            prompt_tokens=prompt_tokens_total,
            completion_tokens=completion_tokens_total,
            total_tokens=total_tokens_acc,
        )
        db.commit()
        db.refresh(run)
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            token_usage=run.token_usage,
            pending_tool=run.pending_tool,
            final_answer=run.final_answer,
        )
        return run

    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        if total_tokens_acc:
            run.token_usage = total_tokens_acc
            _log_agent_usage(
                db,
                run,
                prompt_tokens=prompt_tokens_total,
                completion_tokens=completion_tokens_total,
                total_tokens=total_tokens_acc,
            )
        db.commit()
        db.refresh(run)
        raise
