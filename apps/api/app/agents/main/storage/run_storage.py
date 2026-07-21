"""Agent run storage hygiene: compact heavy step payloads and prune old runs.

Visual / planner steps often embed full prompts and llm_output JSON in
step.input / step.output. That is useful live, but bloats Postgres for
finished history. Compact completed runs and drop aged history so free-tier
DBs stay healthy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import AgentRun, AgentStep

# Keys that dominate storage on visual tool_result / tool_call steps.
_HEAVY_KEYS = (
    "prompt",
    "llm_output",
    "replan_prompt",
    "replan_llm_output",
    "structured_input",
    "structured_handoff",
)


def _truncate_str(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def compact_json_value(value: Any, *, max_str: int = 400) -> Any:
    """Drop or truncate bulky fields while keeping status/meta for the UI."""
    if value is None:
        return None
    if isinstance(value, str):
        return _truncate_str(value, max_str)
    if isinstance(value, list):
        # Keep short lists; truncate long ones.
        if len(value) > 40:
            return [compact_json_value(v, max_str=max_str) for v in value[:40]] + [
                f"… +{len(value) - 40} more"
            ]
        return [compact_json_value(v, max_str=max_str) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if key in _HEAVY_KEYS:
                if isinstance(v, str):
                    out[key] = f"[compacted {len(v)} chars]"
                elif v is not None:
                    out[key] = "[compacted]"
                continue
            # Nested specs stay but strings inside get truncated.
            if key in ("spec", "layout_plan", "presentation_spec") and isinstance(v, dict):
                out[key] = v  # keep full presentation for re-open
                continue
            out[key] = compact_json_value(v, max_str=max_str)
        return out
    return value


def compact_agent_step(step: AgentStep, *, max_str: int = 400) -> bool:
    """Compact one step in-place. Returns True if anything changed."""
    before_in = step.input
    before_out = step.output
    new_in = compact_json_value(before_in, max_str=max_str)
    new_out = compact_json_value(before_out, max_str=max_str)
    changed = new_in != before_in or new_out != before_out
    if changed:
        step.input = new_in
        step.output = new_out
    return changed


def compact_run_steps(db: Session, run: AgentRun, *, max_str: int = 400) -> int:
    """Compact all steps on a finished run. Returns number of steps changed."""
    changed = 0
    for step in run.steps or []:
        if compact_agent_step(step, max_str=max_str):
            changed += 1
    if changed:
        db.flush()
    return changed


def compact_run_if_terminal(db: Session, run: AgentRun) -> int:
    """Compact when the run is no longer live (completed / failed / cancelled)."""
    if not getattr(settings, "agent_step_compact_on_complete", True):
        return 0
    status = (run.status or "").lower()
    if status in ("running", "waiting_approval"):
        return 0
    return compact_run_steps(db, run)


def prune_agent_runs(
    db: Session,
    *,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    retention_days: int | None = None,
    max_per_workspace: int | None = None,
) -> dict[str, int]:
    """
    Delete aged / excess agent runs (cascade deletes steps).

    - retention_days: drop terminal runs older than this
    - max_per_workspace: keep only the newest N runs per workspace (any status
      except running — never delete an active run)
    """
    days = (
        retention_days
        if retention_days is not None
        else int(getattr(settings, "agent_run_retention_days", 30) or 0)
    )
    cap = (
        max_per_workspace
        if max_per_workspace is not None
        else int(getattr(settings, "agent_run_max_per_workspace", 50) or 0)
    )
    deleted_age = 0
    deleted_cap = 0

    terminal = ("completed", "failed", "cancelled", "error")

    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = db.query(AgentRun).filter(
            AgentRun.status.in_(terminal),
            AgentRun.created_at < cutoff,
        )
        if user_id is not None:
            q = q.filter(AgentRun.user_id == user_id)
        if workspace_id is not None:
            q = q.filter(AgentRun.workspace_id == workspace_id)
        rows = q.all()
        for run in rows:
            db.delete(run)
            deleted_age += 1

    if cap > 0:
        # Per-workspace newest-N keep for this user (or all if no user filter).
        scope_q = db.query(AgentRun.workspace_id).distinct()
        if user_id is not None:
            scope_q = scope_q.filter(AgentRun.user_id == user_id)
        if workspace_id is not None:
            scope_q = scope_q.filter(AgentRun.workspace_id == workspace_id)
        workspace_ids = [row[0] for row in scope_q.all()]
        for ws_id in workspace_ids:
            runs = (
                db.query(AgentRun)
                .filter(
                    AgentRun.workspace_id == ws_id,
                    AgentRun.status != "running",
                )
                .order_by(AgentRun.created_at.desc())
                .all()
            )
            if user_id is not None:
                runs = [r for r in runs if r.user_id == user_id]
            for run in runs[cap:]:
                db.delete(run)
                deleted_cap += 1

    if deleted_age or deleted_cap:
        db.flush()
    return {"deleted_by_age": deleted_age, "deleted_by_cap": deleted_cap}


def load_run_for_resume(
    db: Session,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .options(joinedload(AgentRun.steps))
        .filter(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .first()
    )
