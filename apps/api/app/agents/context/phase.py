"""Context phase entry points: start HITL questions, resume into main agent."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.agents.context.curator import curate_main_agent_prompt
from app.agents.context.llm import generate_questions
from app.agents.context.merge import answers_to_snapshot, format_collected_context
from app.agents.context.readiness import assess_readiness
from app.agents.context.workspace_apply import apply_snapshot_to_workspace
from app.agents.main.profiles import agent_system_prompt, get_profile
from app.agents.main.run_policy import (
    apply_snapshot_to_tool_policy,
    apply_tool_policy_to_base_prompt,
    format_run_tool_policy_block,
    run_requires_date_tool,
)
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
from app.models import AgentRun, Workspace

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
    Pause for plan follow-up HITL before any main tools.

    When ``context_agent_always`` is True (default / option 1A), always ask
    plan setup questions. Otherwise only when readiness finds gaps.

    Returns True when the run is waiting for user input (caller should return).
    Returns False when main can start immediately.
    """
    if not getattr(settings, "context_agent_enabled", True):
        return False

    always = bool(getattr(settings, "context_agent_always", True))
    gaps = assess_readiness(packet, run.goal or "")
    if not always and not gaps:
        return False

    form = generate_questions(
        packet,
        run.goal or "",
        gaps,
        always=always,
    )
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
            or "Set up this plan",
            "subtitle": form.get("subtitle")
            or "Answer what you can — skip optional fields if unsure.",
            "questions": questions,
        },
        "checkpoint": {
            "phase": "context",
            "gaps": [g.id for g in gaps],
            "always": always,
            "max_steps": max_steps,
            "agent_type": run.agent_type or "general",
        },
    }
    run.final_answer = (
        "Before tools run, answer a few questions about this plan "
        "(or skip to continue with what we have)."
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
            "always": always,
            "goal": (run.goal or "")[:300],
        },
        output={
            "status": "waiting_input",
            "kind": "questions",
            "question_count": len(questions),
            "always": always,
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
        message="waiting for plan context from user",
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
    """User submitted (or skipped) context questions — curate prompt, then main loop."""
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

    # Persist into workspace Settings when fields are empty.
    workspace = db.get(Workspace, run.workspace_id)
    workspace_update: dict[str, Any] = {"updated": False}
    if workspace is not None and not snapshot.is_empty():
        workspace_update = apply_snapshot_to_workspace(db, workspace, snapshot)
        if workspace_update.get("updated"):
            step_index = _next_step_index(db, run.id)
            _append_step(
                db,
                run,
                step_index=step_index,
                type="context_merge",
                tool_name="workspace_context",
                input={"snapshot": snapshot.to_dict()},
                output={
                    "status": "merged",
                    "workspace_id": str(workspace.id),
                    "changes": {
                        k: v
                        for k, v in workspace_update.items()
                        if k != "updated"
                    },
                },
                on_event=on_event,
            )
            # Refresh packet after description/tags change.
            run._workspace_context = resolve_workspace_context(  # type: ignore[attr-defined]
                db, run.workspace_id, user_id=run.user_id
            )

    if getattr(run, "_workspace_context", None) is None:
        run._workspace_context = resolve_workspace_context(  # type: ignore[attr-defined]
            db, run.workspace_id, user_id=run.user_id
        )
    packet: WorkspaceContextPacket = run._workspace_context  # type: ignore[attr-defined]

    # Honor HITL evidence plan (docs-only vs web) before binding tools.
    policy_summary = apply_snapshot_to_tool_policy(packet, snapshot)
    allow_web = bool(policy_summary.get("allow_web_search", packet.derived.tool_policy.external_context_ok))
    allow_fetch = bool(policy_summary.get("allow_fetch_url", allow_web))

    # Curator agent: build main-agent brief + curated goal from workspace context.
    curated = curate_main_agent_prompt(
        packet,
        run.goal or "",
        snapshot,
        policy_summary=policy_summary,
    )
    step_index = _next_step_index(db, run.id)
    _append_step(
        db,
        run,
        step_index=step_index,
        type="context_curate",
        tool_name="prompt_curator",
        input={
            "goal": (run.goal or "")[:300],
            "has_snapshot": not snapshot.is_empty(),
            "tool_policy": policy_summary,
        },
        output={
            "status": "ok",
            "source": curated.get("source"),
            "model": curated.get("model"),
            "rationale": curated.get("rationale"),
            "curated_goal": (curated.get("curated_goal") or "")[:500],
            "system_addendum_preview": (curated.get("system_addendum") or "")[:400],
            "tool_policy": policy_summary,
        },
        on_event=on_event,
    )

    curated_goal = (curated.get("curated_goal") or run.goal or "").strip()
    require_date = run_requires_date_tool(
        allow_web=allow_web,
        goal=run.goal or "",
        snapshot=snapshot,
        curated_goal=curated_goal,
        allow_fetch_url=allow_fetch,
    )
    run._require_date_tool = require_date  # type: ignore[attr-defined]
    run._allow_web = allow_web  # type: ignore[attr-defined]
    run._allow_fetch_url = allow_fetch  # type: ignore[attr-defined]

    profile = get_profile(agent_type)
    base = apply_tool_policy_to_base_prompt(
        agent_system_prompt(profile.system_prompt),
        require_date=require_date,
        allow_web=allow_web,
        allow_fetch_url=allow_fetch,
    )
    system = format_main_agent_system_prompt(base, packet)
    system = (
        f"{system.rstrip()}\n\n"
        f"{format_run_tool_policy_block(allow_web=allow_web, require_date=require_date, evidence_plan=str(policy_summary.get('evidence_plan') or 'unknown'), ready_doc_count=len(packet.evidence.documents_ready or []), allow_fetch_url=allow_fetch)}"
    )
    addendum = (curated.get("system_addendum") or "").strip()
    if addendum:
        system = f"{system.rstrip()}\n\n{addendum}"
    collected_block = format_collected_context(snapshot)
    if collected_block:
        system = f"{system.rstrip()}\n\n{collected_block}"
        run._collected_context = snapshot  # type: ignore[attr-defined]

    human = curated_goal
    if snapshot.urls and "http" not in human.lower():
        human = f"{human}\n\n[User provided URLs: {', '.join(snapshot.urls)}]"

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=human),
    ]

    run.status = "running"
    run.pending_tool = None
    run.final_answer = None
    # Store curated goal + tool policy for UI/debug without changing AgentRun.goal.
    opts = dict(run.run_options or {}) if isinstance(run.run_options, dict) else {}
    opts["curated_goal"] = human[:2000]
    opts["context_curator_source"] = curated.get("source")
    opts["tool_policy"] = {
        **policy_summary,
        "require_date": require_date,
        "allow_web": allow_web,
        "allow_web_search": allow_web,
        "allow_fetch_url": allow_fetch,
    }
    run.run_options = opts
    db.commit()

    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status="running",
        message="starting main agent with curated workspace context",
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
