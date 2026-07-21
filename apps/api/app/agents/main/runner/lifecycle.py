"""Run lifecycle entry points: start a run, approve/reject, resume, visual phase."""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.orm import Session

from app.agents.main.trace.execution_trace import LiveTraceContext
from app.agents.main.profiles import agent_system_prompt, get_profile
from app.agents.main.runner.constants import WRITE_TOOLS
from app.agents.main.runner.events import (
    EventCallback,
    _append_step,
    _emit,
    _next_step_index,
    _refresh_execution_trace,
)
from app.agents.main.runner.loop import _run_tool_loop
from app.agents.main.runner.messages import _deserialize_messages
from app.agents.visual_summary.pipeline import (
    _is_presentation_pending,
    _presentation_context_for_run,
    _run_visual_pipeline,
    _visual_summary_handoff_message,
)
from app.agents.main.tools import build_tools
from app.agents.visual_summary.tools import VISUAL_SUMMARY_AGENT_LABEL
from app.config import settings
from app.models import AgentRun
from app.agents.visual_summary.handoff.extract import handoff_error_message, validate_handoff
from app.agents.visual_summary.workspace.context import (
    format_main_agent_system_prompt,
    resolve_workspace_context,
)


def run_agent(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    goal: str,
    max_steps: int = 5,
    agent_type: str = "general",
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Tool loop with human approval for write tools.

    Read tools run immediately. Write tools pause at waiting_approval;
    approve_agent_run() executes the write and **resumes** the agent loop.
    """
    goal = goal.strip()
    if not goal:
        raise ValueError("goal is empty")

    profile = get_profile(agent_type)
    resolved_type = profile.agent_type
    cap_steps = max(1, min(max_steps, 12))

    run = AgentRun(
        workspace_id=workspace_id,
        user_id=user_id,
        goal=goal,
        agent_type=resolved_type,
        status="running",
        pending_tool=None,
    )
    db.add(run)
    db.flush()

    packet = resolve_workspace_context(db, workspace_id, user_id=user_id)
    run._workspace_context = packet  # type: ignore[attr-defined]
    system = format_main_agent_system_prompt(
        agent_system_prompt(profile.system_prompt),
        packet,
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=system),
        HumanMessage(content=goal),
    ]
    _emit(
        on_event,
        "run_start",
        run_id=str(run.id),
        goal=goal,
        workspace_id=str(workspace_id),
        agent_type=resolved_type,
        status="running",
        workspace_context={
            "confidence": packet.meta.confidence,
            "derivation_version": packet.meta.derivation_version,
            "outcome_phrase": packet.derived.outcome_phrase,
            "tone": packet.derived.tone,
            "external_context_ok": packet.derived.tool_policy.external_context_ok,
            "visual_affordances": list(packet.derived.visual_affordances),
        },
    )
    trace_live = LiveTraceContext()
    run._trace_live = trace_live  # type: ignore[attr-defined]
    _refresh_execution_trace(db, run, on_event, trace_live)
    return _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=cap_steps,
        start_step_index=0,
        on_event=on_event,
        trace_live=trace_live,
    )


def _run_visual_summary_agent(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    on_event: EventCallback = None,
    trace_live: LiveTraceContext | None = None,
) -> AgentRun:
    """Run the Visual Summary Agent after the user approves generative UI."""
    if run.presentation_spec:
        return run

    if trace_live is not None:
        trace_live.visual_agent_active = True

    ctx = _presentation_context_for_run(db, run)
    handoff_ok, handoff_errors = validate_handoff(ctx.structured_content)
    if not handoff_ok:
        step_index += 1
        message = handoff_error_message(handoff_errors)
        _append_step(
            db,
            run,
            step_index=step_index,
            type="agent_handoff",
            input={
                "from": run.agent_type or "general",
                "to": "visual_summary",
                "goal": run.goal,
                "answer_preview": (run.final_answer or "")[:500],
            },
            output={"status": "handoff_failed", "errors": handoff_errors},
            on_event=on_event,
        )
        run.status = "failed"
        run.error = message
        db.commit()
        db.refresh(run)
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            final_answer=run.final_answer,
        )
        if trace_live is not None:
            trace_live.visual_agent_active = False
        return run

    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="agent_handoff",
        input={
            "from": run.agent_type or "general",
            "to": "visual_summary",
            "goal": run.goal,
            "answer_preview": (run.final_answer or "")[:500],
        },
        output={"status": "handoff", "agent": VISUAL_SUMMARY_AGENT_LABEL},
        on_event=on_event,
    )

    if not settings.visual_summary_agent_loop:
        # Default: code orchestrator — plan_layout → render_ui directly.
        # The outer agent added LLM turns but no decisions (render_ui already
        # accepts "{}" and uses the plan produced by plan_layout).
        completed = _run_visual_pipeline(
            db,
            run,
            ctx=ctx,
            step_index=step_index,
            on_event=on_event,
        )
        if trace_live is not None:
            trace_live.visual_agent_active = False
        return completed

    profile = get_profile("visual_summary")
    messages: list[BaseMessage] = [
        SystemMessage(content=agent_system_prompt(profile.system_prompt)),
        HumanMessage(content=_visual_summary_handoff_message(ctx)),
    ]
    chat_model = settings.visual_summary_model
    completed = _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=profile.default_max_steps,
        start_step_index=step_index,
        on_event=on_event,
        trace_live=trace_live,
        agent_type_override="visual_summary",
        presentation_context=ctx,
        chat_model=chat_model,
        finalize_mode="visual_summary",
        initial_token_usage=int(run.token_usage or 0),
    )
    return completed


def approve_agent_run(
    db: Session,
    run: AgentRun,
    *,
    approve: bool,
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Approve or reject a pending write tool.

    On approve: execute the write, append the tool result, then **resume**
    the LLM tool loop so the agent can continue (confirm, next steps, etc.).
    On reject: mark cancelled (no resume).
    """
    if run.status != "waiting_approval" or not run.pending_tool:
        raise ValueError("Run is not waiting for approval")

    trace_live = getattr(run, "_trace_live", None) or LiveTraceContext()
    run._trace_live = trace_live  # type: ignore[attr-defined]

    pending = dict(run.pending_tool)
    name = pending.get("name")
    args = pending.get("args") or {}
    call_id = pending.get("id") or str(uuid.uuid4())
    checkpoint = pending.get("checkpoint") if isinstance(pending.get("checkpoint"), dict) else {}
    step_index = _next_step_index(db, run.id)

    if not approve:
        _append_step(
            db,
            run,
            step_index=step_index,
            type="approval",
            tool_name=name,
            input=args,
            output={"status": "rejected"},
            on_event=on_event,
        )
        if _is_presentation_pending(pending):
            run.status = "completed"
            run.pending_tool = None
        else:
            run.status = "cancelled"
            run.pending_tool = None
            run.final_answer = f"Write action `{name}` was rejected by the user."
        from app.agents.main.storage.run_storage import compact_run_if_terminal

        compact_run_if_terminal(db, run)
        db.commit()
        db.refresh(run)
        return run

    if _is_presentation_pending(pending):
        trace_live.approving = True
        trace_live.visual_agent_active = True
        _refresh_execution_trace(db, run, on_event, trace_live)
        _append_step(
            db,
            run,
            step_index=step_index,
            type="approval",
            tool_name=name,
            input=args,
            output={"status": "approved"},
            on_event=on_event,
        )
        step_index += 1
        # Main agent work is done — only the visual summary agent should run next.
        run.pending_tool = None
        run.status = "running"
        db.flush()
        _run_visual_summary_agent(
            db,
            run,
            step_index=step_index,
            on_event=on_event,
            trace_live=trace_live,
        )
        run.status = "completed"
        from app.agents.main.storage.run_storage import compact_run_if_terminal

        compact_run_if_terminal(db, run)
        db.commit()
        db.refresh(run)
        trace_live.approving = False
        trace_live.visual_agent_active = False
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            final_answer=run.final_answer,
            presentation_spec=run.presentation_spec,
        )
        _refresh_execution_trace(db, run, on_event, trace_live)
        return run

    if name not in WRITE_TOOLS:
        raise ValueError(f"Pending tool is not a write tool: {name}")

    if getattr(run, "_workspace_context", None) is None:
        run._workspace_context = resolve_workspace_context(  # type: ignore[attr-defined]
            db, run.workspace_id, user_id=run.user_id
        )
    packet = run._workspace_context  # type: ignore[attr-defined]
    tools = {
        t.name: t
        for t in build_tools(
            db,
            workspace_id=run.workspace_id,
            user_id=run.user_id or uuid.UUID(int=0),
            agent_type=run.agent_type,
            allow_web_search=bool(packet.derived.tool_policy.external_context_ok),
        )
    }
    tool = tools.get(name)
    if not tool:
        raise ValueError(f"Tool not found: {name}")

    try:
        result = tool.invoke(args)
    except Exception as e:
        _append_step(
            db,
            run,
            step_index=step_index,
            type="tool_result",
            tool_name=name,
            input=args,
            output={"error": str(e)},
            on_event=on_event,
        )
        run.status = "failed"
        run.error = str(e)
        run.pending_tool = None
        db.commit()
        db.refresh(run)
        return run

    _append_step(
        db,
        run,
        step_index=step_index,
        type="approval",
        tool_name=name,
        input=args,
        output={"status": "approved"},
        on_event=on_event,
    )
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_result",
        tool_name=name,
        input=args,
        output=result,
        on_event=on_event,
    )

    # Rebuild conversation and append successful write result
    messages = _deserialize_messages(checkpoint.get("messages") or [])
    if not messages:
        # Fallback if old runs lack checkpoint
        profile = get_profile(run.agent_type)
        system = format_main_agent_system_prompt(
            agent_system_prompt(profile.system_prompt),
            packet,
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=run.goal or ""),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": call_id,
                        "name": name,
                        "args": args,
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    messages.append(
        ToolMessage(
            content=json.dumps(result, default=str),
            tool_call_id=str(call_id),
            name=str(name),
        )
    )
    # Nudge: write is done; produce a final confirmation / next steps
    messages.append(
        HumanMessage(
            content=(
                f"[System] The user approved and `{name}` executed successfully. "
                f"Result: {json.dumps(result, default=str)}. "
                "Continue: briefly confirm what was done and any useful next steps. "
                "Do not call create_note again unless the user clearly asked for another note."
            )
        )
    )

    run.status = "running"
    run.pending_tool = None
    run.final_answer = None
    db.commit()

    remaining = int(checkpoint.get("max_steps") or 5)
    # Allow a few more steps after approval to finish cleanly
    resume_steps = max(2, min(remaining, 8))

    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status="running",
        message="resuming after approval",
    )
    return _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=resume_steps,
        prompt_tokens_total=int(checkpoint.get("prompt_tokens") or 0),
        completion_tokens_total=int(checkpoint.get("completion_tokens") or 0),
        total_tokens_acc=int(checkpoint.get("total_tokens") or 0),
        start_step_index=step_index,
        on_event=on_event,
    )
