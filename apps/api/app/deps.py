import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.logging_config import user_id_ctx
from app.models import User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=True)


def _touch_last_seen(db: Session, user: User) -> None:
    """Update last_seen_at at most every N seconds (avoids write storms)."""
    now = datetime.now(timezone.utc)
    throttle = max(30, int(settings.monitoring_seen_throttle_seconds or 300))
    seen = user.last_seen_at
    if seen is not None:
        # Normalize naive timestamps from SQLite tests
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if now - seen < timedelta(seconds=throttle):
            return
    user.last_seen_at = now
    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:

    user_id = decode_access_token(creds.credentials)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        )
    user = db.get(User, uid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    # Correlate later logs in this request with the authenticated user
    user_id_ctx.set(str(user.id))
    _touch_last_seen(db, user)
    return user


def user_is_admin(user: User) -> bool:
    """True if ADMIN_EMAILS is empty (open) or the user email is listed."""
    raw = (settings.admin_emails or "").strip()
    if not raw:
        return True
    allowed = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return (user.email or "").lower() in allowed


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user_is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Monitoring is restricted to admin users",
        )
    return user
