"""Step persistence, SSE event emission, and public run/step serialization."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.agents.trace.execution_trace import (
    LiveTraceContext,
    build_execution_trace,
    emit_execution_trace,
)
from app.models import AgentRun, AgentStep, Workspace

# on_event(event_type, payload) — used for LangSmith-style live traces (SSE)
EventCallback = Callable[[str, dict[str, Any]], None] | None


def _emit(on_event: EventCallback, event_type: str, **payload: Any) -> None:
    if on_event:
        on_event(event_type, payload)


def step_to_dict(step: AgentStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "step_index": step.step_index,
        "type": step.type,
        "tool_name": step.tool_name,
        "input": step.input,
        "output": step.output,
        "created_at": step.created_at.isoformat() if step.created_at else None,
    }


def _workspace_name_for_run(db: Session, run: AgentRun) -> str | None:
    ws = db.get(Workspace, run.workspace_id)
    return ws.name if ws else None


def run_to_public_dict(
    run: AgentRun,
    *,
    trace_live: LiveTraceContext | None = None,
    workspace_name: str | None = None,
) -> dict[str, Any]:
    steps = sorted(run.steps or [], key=lambda s: s.step_index)
    return {
        "id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "user_id": str(run.user_id) if run.user_id else None,
        "goal": run.goal,
        "agent_type": run.agent_type or "general",
        "presentation_spec": run.presentation_spec,
        "status": run.status,
        "final_answer": run.final_answer,
        "error": run.error,
        "token_usage": run.token_usage,
        "pending_tool": run.pending_tool,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "steps": [step_to_dict(s) for s in steps],
        "execution_trace": build_execution_trace(
            run,
            live=trace_live,
            workspace_name=workspace_name,
        ),
    }


def _refresh_execution_trace(
    db: Session,
    run: AgentRun,
    on_event: EventCallback,
    trace_live: LiveTraceContext | None,
) -> None:
    if not on_event:
        return
    db.refresh(run)
    emit_execution_trace(
        on_event,
        run,
        trace_live,
        workspace_name=_workspace_name_for_run(db, run),
    )


def _append_step(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    type: str,
    tool_name: str | None = None,
    input: Any = None,
    output: Any = None,
    on_event: EventCallback = None,
    duration_ms: float | None = None,
) -> AgentStep:
    step = AgentStep(
        run_id=run.id,
        step_index=step_index,
        type=type,
        tool_name=tool_name,
        input=input,
        output=output,
    )
    db.add(step)
    db.flush()
    db.refresh(step)
    payload = step_to_dict(step)
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 1)
    _emit(on_event, "step", step=payload, run_id=str(run.id), status=run.status)
    _refresh_execution_trace(
        db,
        run,
        on_event,
        getattr(run, "_trace_live", None),
    )
    return step


def _next_step_index(db: Session, run_id: uuid.UUID) -> int:
    last = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id)
        .order_by(AgentStep.step_index.desc())
        .first()
    )
    return (last.step_index + 1) if last else 1
