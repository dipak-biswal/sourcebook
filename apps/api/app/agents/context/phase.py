"""Context phase entry points: start HITL questions, resume into main agent."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.agents.context.llm import generate_questions
from app.agents.context.merge import answers_to_snapshot, format_collected_context
from app.agents.context.readiness import assess_readiness
from app.agents.main.profiles import agent_system_prompt, get_profile
from app.agents.main.runner.events import (
    EventCallback,
    _append_step,
    _emit,
    _next_step_index,
    _refresh_execution_trace,
)
from app.agents.main.trace.execution_trace import LiveTraceContext
from app.agents.visual_summary.workspace.context import (
    WorkspaceContextPacket,
    format_main_agent_system_prompt,
    resolve_workspace_context,
)
from app.config import settings
from app.models import AgentRun

CONTEXT_TOOL = "ask_user"

# Injected to avoid circular imports with lifecycle → loop.
ToolLoopFn = Callable[..., AgentRun]


def is_questions_pending(pending: dict[str, Any] | None) -> bool:
    if not pending:
        return False
    return pending.get("kind") == "questions" or pending.get("name") == CONTEXT_TOOL


def start_context_phase_if_needed(
    db: Session,
    run: AgentRun,
    *,
    packet: WorkspaceContextPacket,
    max_steps: int,
    on_event: EventCallback = None,
    trace_live: LiveTraceContext | None = None,
) -> bool:
    """
    If readiness finds gaps, pause the run with a questions form.

    Returns True when the run is waiting for user input (caller should return).
    Returns False when main can start immediately.
    """
    if not getattr(settings, "context_agent_enabled", True):
        return False

    gaps = assess_readiness(packet, run.goal or "")
    if not gaps:
        return False

    form = generate_questions(packet, run.goal or "", gaps)
    questions = form.get("questions") or []
    if not questions:
        return False

    run.status = "waiting_approval"
    run.pending_tool = {
        "id": str(uuid.uuid4()),
        "name": CONTEXT_TOOL,
        "kind": "questions",
        "args": {
            "title": form.get("title")
            or "A bit more context will improve the answer",
            "subtitle": form.get("subtitle")
            or "Answer what you can — skip optional fields if unsure.",
            "questions": questions,
        },
        "checkpoint": {
            "phase": "context",
            "gaps": [g.id for g in gaps],
            "max_steps": max_steps,
            "agent_type": run.agent_type or "general",
        },
    }
    run.final_answer = (
        "Before running, Sourcebook needs a bit more context. "
        "Please answer the questions below (or skip to continue with what we have)."
    )

    _append_step(
        db,
        run,
        step_index=1,
        type="context_check",
        tool_name=CONTEXT_TOOL,
        input={
            "gaps": [g.id for g in gaps],
            "reasons": [g.reason for g in gaps],
        },
        output={
            "status": "waiting_input",
            "kind": "questions",
            "question_count": len(questions),
        },
        on_event=on_event,
    )
    _append_step(
        db,
        run,
        step_index=2,
        type="approval",
        tool_name=CONTEXT_TOOL,
        input=run.pending_tool.get("args"),
        output={
            "status": "waiting_approval",
            "kind": "questions",
        },
        on_event=on_event,
    )
    db.commit()
    db.refresh(run)

    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status="waiting_approval",
        pending_tool=run.pending_tool,
        final_answer=run.final_answer,
        message="waiting for context from user",
    )
    if trace_live is not None:
        _refresh_execution_trace(db, run, on_event, trace_live)
    return True


def resume_after_context_answers(
    db: Session,
    run: AgentRun,
    *,
    answers: dict[str, Any] | None,
    on_event: EventCallback = None,
    run_tool_loop: ToolLoopFn,
    trace_live: LiveTraceContext | None = None,
) -> AgentRun:
    """User submitted (or skipped) context questions — start the main tool loop."""
    pending = dict(run.pending_tool or {})
    args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    questions = args.get("questions") if isinstance(args, dict) else []
    checkpoint = (
        pending.get("checkpoint")
        if isinstance(pending.get("checkpoint"), dict)
        else {}
    )
    max_steps = int(checkpoint.get("max_steps") or 5)
    agent_type = str(checkpoint.get("agent_type") or run.agent_type or "general")

    snapshot = answers_to_snapshot(
        answers if isinstance(answers, dict) else {},
        questions=questions if isinstance(questions, list) else [],
    )

    step_index = _next_step_index(db, run.id)
    _append_step(
        db,
        run,
        step_index=step_index,
        type="approval",
        tool_name=CONTEXT_TOOL,
        input={"answers": answers or {}},
        output={
            "status": "approved",
            "kind": "questions",
            "collected": snapshot.to_dict() if not snapshot.is_empty() else {},
        },
        on_event=on_event,
    )

    if getattr(run, "_workspace_context", None) is None:
        run._workspace_context = resolve_workspace_context(  # type: ignore[attr-defined]
            db, run.workspace_id, user_id=run.user_id
        )
    packet: WorkspaceContextPacket = run._workspace_context  # type: ignore[attr-defined]

    profile = get_profile(agent_type)
    system = format_main_agent_system_prompt(
        agent_system_prompt(profile.system_prompt),
        packet,
    )
    collected_block = format_collected_context(snapshot)
    if collected_block:
        system = f"{system.rstrip()}\n\n{collected_block}"
        run._collected_context = snapshot  # type: ignore[attr-defined]

    human = (run.goal or "").strip()
    if snapshot.topic_focus:
        human = f"{human}\n\n[User clarified focus: {snapshot.topic_focus}]"
    if snapshot.urls:
        human = f"{human}\n\n[User provided URLs: {', '.join(snapshot.urls)}]"

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=human),
    ]

    run.status = "running"
    run.pending_tool = None
    run.final_answer = None
    db.commit()

    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status="running",
        message="starting main agent with collected context",
    )
    if trace_live is not None:
        _refresh_execution_trace(db, run, on_event, trace_live)

    return run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=max(1, min(max_steps, 12)),
        start_step_index=step_index,
        on_event=on_event,
        trace_live=trace_live,
    )


def reject_context_phase(
    db: Session,
    run: AgentRun,
    *,
    on_event: EventCallback = None,
) -> AgentRun:
    """User cancelled the context form."""
    from app.agents.main.storage.run_storage import compact_run_if_terminal

    step_index = _next_step_index(db, run.id)
    _append_step(
        db,
        run,
        step_index=step_index,
        type="approval",
        tool_name=CONTEXT_TOOL,
        input={},
        output={"status": "rejected", "kind": "questions"},
        on_event=on_event,
    )
    run.status = "cancelled"
    run.pending_tool = None
    run.final_answer = "Context setup was cancelled before the agent ran."
    compact_run_if_terminal(db, run)
    db.commit()
    db.refresh(run)
    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status=run.status,
        final_answer=run.final_answer,
    )
    return run
