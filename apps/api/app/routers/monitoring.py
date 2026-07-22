"""User activity monitoring for Settings → Monitoring."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_admin
from app.models import User

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class MonitoringUserRow(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    last_seen_at: datetime | None = None
    online: bool = False


class MonitoringOverviewResponse(BaseModel):
    total_users: int
    online_now: int
    active_today: int
    active_7d: int
    online_window_minutes: int = Field(
        description="Users with last_seen within this many minutes count as online"
    )
    users: list[MonitoringUserRow] = Field(default_factory=list)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/users", response_model=MonitoringOverviewResponse)
def monitoring_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Aggregate counts + user activity list for the Monitoring settings tab."""
    _ = current_user
    now = datetime.now(timezone.utc)
    online_mins = max(1, int(settings.monitoring_online_minutes or 15))
    online_cutoff = now - timedelta(minutes=online_mins)
    day_cutoff = now - timedelta(hours=24)
    week_cutoff = now - timedelta(days=7)

    rows = db.query(User).order_by(User.created_at.desc()).all()
    online = 0
    active_today = 0
    active_7d = 0
    out: list[MonitoringUserRow] = []

    for u in rows:
        seen = _as_utc(u.last_seen_at)
        login = _as_utc(u.last_login_at)
        # Activity = most recent of login or seen
        activity = seen or login
        is_online = bool(seen and seen >= online_cutoff)
        if is_online:
            online += 1
        if activity and activity >= day_cutoff:
            active_today += 1
        if activity and activity >= week_cutoff:
            active_7d += 1
        out.append(
            MonitoringUserRow(
                id=u.id,
                email=u.email,
                created_at=u.created_at,
                last_login_at=login,
                last_seen_at=seen,
                online=is_online,
            )
        )

    # Online users first, then by last_seen desc
    out.sort(
        key=lambda r: (
            0 if r.online else 1,
            -(r.last_seen_at.timestamp() if r.last_seen_at else 0),
        )
    )

    return MonitoringOverviewResponse(
        total_users=len(rows),
        online_now=online,
        active_today=active_today,
        active_7d=active_7d,
        online_window_minutes=online_mins,
        users=out,
    )
