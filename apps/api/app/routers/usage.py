import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import AgentRun, AgentStep, Message, UsageEvent, User, WorkspaceMember
from app.presentation.interactions import (
    ACTION_TO_AFFORDANCE,
    ALLOWED_ACTIONS,
    log_visual_interaction,
)

router = APIRouter(prefix="/usage", tags=["usage"])


class DailyTotal(BaseModel):
    date: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    event_count: int


class UsageEventResponse(BaseModel):
    id: uuid.UUID
    kind: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    meta: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UsageSummaryResponse(BaseModel):
    event_count: int
    total_tokens: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    recent: list[UsageEventResponse] = Field(default_factory=list)
    daily_totals: list[DailyTotal] = Field(default_factory=list)


def _to_event_response(row: UsageEvent) -> UsageEventResponse:
    """Convert ORM row → schema (avoids nested from_attributes issues)."""
    meta = row.meta
    if meta is not None and not isinstance(meta, dict):
        meta = None
    return UsageEventResponse(
        id=row.id,
        kind=row.kind,
        model=row.model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        meta=meta,
        created_at=row.created_at,
    )


@router.get("/events", response_model=list[UsageEventResponse])
def list_usage_events(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent usage rows for the logged-in user."""
    rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == current_user.id)
        .order_by(UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_to_event_response(r) for r in rows]


@router.get("/summary", response_model=UsageSummaryResponse)
def usage_summary(
    recent_limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate totals + recent events for the current user."""
    rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == current_user.id)
        .order_by(UsageEvent.created_at.desc())
        .limit(recent_limit)
        .all()
    )

    total = (
        db.query(func.coalesce(func.sum(UsageEvent.total_tokens), 0))
        .filter(UsageEvent.user_id == current_user.id)
        .scalar()
    )
    count = (
        db.query(func.count(UsageEvent.id))
        .filter(UsageEvent.user_id == current_user.id)
        .scalar()
    )

    kind_rows = (
        db.query(
            UsageEvent.kind,
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        )
        .filter(UsageEvent.user_id == current_user.id)
        .group_by(UsageEvent.kind)
        .all()
    )
    by_kind = {str(kind): int(tokens or 0) for kind, tokens in kind_rows}

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily_rows = (
        db.query(
            cast(UsageEvent.created_at, Date).label("day"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
            func.count(UsageEvent.id),
        )
        .filter(UsageEvent.user_id == current_user.id)
        .filter(UsageEvent.created_at >= thirty_days_ago)
        .group_by(cast(UsageEvent.created_at, Date))
        .order_by(cast(UsageEvent.created_at, Date))
        .all()
    )
    daily_totals = [
        DailyTotal(
            date=str(row[0]),
            total_tokens=int(row[1] or 0),
            prompt_tokens=int(row[2] or 0),
            completion_tokens=int(row[3] or 0),
            event_count=int(row[4] or 0),
        )
        for row in daily_rows
    ]

    return UsageSummaryResponse(
        event_count=int(count or 0),
        total_tokens=int(total or 0),
        by_kind=by_kind,
        recent=[_to_event_response(r) for r in rows],
        daily_totals=daily_totals,
    )


_VISUAL_PIPELINE_KINDS = (
    "visual_summary_plan_outcome",
    "visual_summary_render",
    "visual_summary_plan",
    "presentation",
)


class VisualPipelineSummary(BaseModel):
    """Aggregated quality/cost signals for the Visual Summary pipeline."""

    plan_count: int = 0
    render_count: int = 0
    validation_failed_rate: float = 0.0
    replan_rate: float = 0.0
    skeleton_fallback_rate: float = 0.0
    render_fallback_rate: float = 0.0
    avg_block_count: float = 0.0
    dropped_block_total: int = 0
    tokens_by_kind: dict[str, int] = Field(default_factory=dict)


def summarize_visual_pipeline(rows: list[UsageEvent]) -> VisualPipelineSummary:
    """Fold usage rows (any kinds) into pipeline health rates."""
    plan_count = 0
    render_count = 0
    validation_failed = 0
    replans = 0
    skeleton_fallbacks = 0
    render_fallbacks = 0
    block_count_total = 0
    dropped_total = 0
    tokens_by_kind: dict[str, int] = {}

    for row in rows:
        kind = str(row.kind or "")
        if kind not in _VISUAL_PIPELINE_KINDS:
            continue
        meta = row.meta if isinstance(row.meta, dict) else {}
        tokens_by_kind[kind] = tokens_by_kind.get(kind, 0) + int(row.total_tokens or 0)
        if kind == "visual_summary_plan_outcome":
            plan_count += 1
            if meta.get("validation_status") == "failed":
                validation_failed += 1
            if meta.get("replan_attempted"):
                replans += 1
            if meta.get("planner_source") == "skeleton":
                skeleton_fallbacks += 1
        elif kind == "visual_summary_render":
            render_count += 1
            if meta.get("render_fallback_used"):
                render_fallbacks += 1
            block_count_total += int(meta.get("block_count") or 0)
            dropped_total += int(meta.get("dropped_blocks") or 0)

    def rate(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    return VisualPipelineSummary(
        plan_count=plan_count,
        render_count=render_count,
        validation_failed_rate=rate(validation_failed, plan_count),
        replan_rate=rate(replans, plan_count),
        skeleton_fallback_rate=rate(skeleton_fallbacks, plan_count),
        render_fallback_rate=rate(render_fallbacks, render_count),
        avg_block_count=round(block_count_total / render_count, 2) if render_count else 0.0,
        dropped_block_total=dropped_total,
        tokens_by_kind=tokens_by_kind,
    )


@router.get("/visual-summary", response_model=VisualPipelineSummary)
def visual_pipeline_summary(
    workspace_id: uuid.UUID | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Health of the Visual Summary pipeline: fallback and validation rates."""
    q = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == current_user.id)
        .filter(UsageEvent.kind.in_(_VISUAL_PIPELINE_KINDS))
    )
    if workspace_id is not None:
        q = q.filter(UsageEvent.workspace_id == workspace_id)
    rows = q.order_by(UsageEvent.created_at.desc()).limit(limit).all()
    return summarize_visual_pipeline(rows)


class VisualInteractionIn(BaseModel):
    workspace_id: uuid.UUID
    action: str = Field(..., min_length=1, max_length=64)
    affordance: str | None = Field(None, max_length=64)
    label: str | None = Field(None, max_length=120)
    run_id: uuid.UUID | None = None


class VisualInteractionOut(BaseModel):
    status: str = "ok"
    action: str
    affordance: str | None = None


@router.post("/visual-interactions", response_model=VisualInteractionOut, status_code=201)
def post_visual_interaction(
    body: VisualInteractionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a chip click / FAQ expand so future layouts rank what users open."""
    action = body.action.strip().lower()
    if action not in ALLOWED_ACTIONS and action not in ACTION_TO_AFFORDANCE:
        # Allow any action that maps or is explicitly listed; reject garbage.
        if action not in ACTION_TO_AFFORDANCE and not body.affordance:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown action '{action}' (expected one of "
                f"{sorted(ACTION_TO_AFFORDANCE)} or affordance_open with affordance)",
            )
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == body.workspace_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    event = log_visual_interaction(
        db,
        user_id=current_user.id,
        workspace_id=body.workspace_id,
        action=action,
        affordance=body.affordance,
        label=body.label,
        run_id=str(body.run_id) if body.run_id else None,
    )
    db.commit()
    meta = event.meta if isinstance(event.meta, dict) else {}
    return VisualInteractionOut(
        status="ok",
        action=action,
        affordance=meta.get("affordance"),
    )


class UsageDetailResponse(BaseModel):
    kind: str
    goal: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str | None = None
    token_usage: int | None = None
    user_message: str | None = None
    assistant_message: str | None = None
    citations: list[str] = Field(default_factory=list)
    meta: dict[str, Any] | None = None


@router.get("/events/{event_id}", response_model=UsageDetailResponse)
def get_usage_event_detail(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch source details for a usage event — agent run steps or chat messages."""
    event = (
        db.query(UsageEvent)
        .filter(UsageEvent.id == event_id, UsageEvent.user_id == current_user.id)
        .first()
    )
    if not event:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    meta = event.meta or {}

    if event.kind == "agent_run":
        run_id = meta.get("run_id")
        if run_id:
            run = (
                db.query(AgentRun)
                .filter(AgentRun.id == run_id, AgentRun.user_id == current_user.id)
                .first()
            )
            if run:
                steps = sorted(run.steps or [], key=lambda s: s.step_index)
                return UsageDetailResponse(
                    kind="agent_run",
                    goal=run.goal,
                    steps=[{"type": s.type, "tool_name": s.tool_name, "input": s.input, "output": s.output} for s in steps],
                    final_answer=run.final_answer,
                    token_usage=run.token_usage,
                )

    elif event.kind in ("chat", "chat_stream", "stream"):
        conversation_id = meta.get("conversation_id")
        if conversation_id:
            msgs = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
                .all()
            )
            user_msg = next((m.content for m in msgs if m.role == "user"), None)
            asst_msg = next((m.content for m in msgs if m.role == "assistant"), None)
            return UsageDetailResponse(
                kind=event.kind,
                user_message=user_msg,
                assistant_message=asst_msg,
                citations=[],
            )

    return UsageDetailResponse(kind=event.kind, meta=meta if meta else None)


@router.delete("/events", status_code=204)
def delete_all_usage_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete all usage events for the current user."""
    db.query(UsageEvent).filter(UsageEvent.user_id == current_user.id).delete()
    db.commit()


@router.delete("/events/{event_id}", status_code=204)
def delete_usage_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a single usage event."""
    row = (
        db.query(UsageEvent)
        .filter(UsageEvent.id == event_id, UsageEvent.user_id == current_user.id)
        .first()
    )
    if not row:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    db.delete(row)
    db.commit()
