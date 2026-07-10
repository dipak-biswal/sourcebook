import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import UsageEvent, User

router = APIRouter(prefix="/usage", tags=["usage"])


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate totals + last 20 events for the current user."""
    rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == current_user.id)
        .order_by(UsageEvent.created_at.desc())
        .limit(20)
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

    return UsageSummaryResponse(
        event_count=int(count or 0),
        total_tokens=int(total or 0),
        by_kind=by_kind,
        recent=[_to_event_response(r) for r in rows],
    )
