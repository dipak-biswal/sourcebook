"""
Dev-only helpers for local testing.

Passwords are hashed in the DB and cannot be recovered. This module only
remembers passwords that you set through these endpoints (in-memory), so the
login page can show them for testing. Memory is cleared when the API restarts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import hash_password

router = APIRouter(prefix="/dev", tags=["dev"])

# email -> last password set via this router (process memory only)
_test_password_hints: dict[str, str] = {}

DEFAULT_TEST_PASSWORD = "password123"


def _require_dev_mode() -> None:
    if not settings.dev_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dev endpoints disabled (set DEV_MODE=true for local testing)",
        )


class DevUserRow(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime | None = None
    test_password: str | None = None
    password_note: str


class DevUserListResponse(BaseModel):
    dev_mode: bool = True
    warning: str
    default_test_password: str = DEFAULT_TEST_PASSWORD
    users: list[DevUserRow]


class SetTestPasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(default=DEFAULT_TEST_PASSWORD, min_length=8, max_length=128)


class SetTestPasswordResponse(BaseModel):
    email: str
    password: str
    message: str


class SetAllPasswordsResponse(BaseModel):
    password: str
    updated: list[str]
    message: str


@router.get("/users", response_model=DevUserListResponse)
def list_users_for_testing(db: Session = Depends(get_db)):
    """List users for local testing. Passwords only if set via this API since restart."""
    _require_dev_mode()
    users = db.query(User).order_by(User.created_at.desc()).all()
    rows: list[DevUserRow] = []
    for u in users:
        email = u.email
        hint = _test_password_hints.get(email.lower())
        rows.append(
            DevUserRow(
                id=u.id,
                email=email,
                created_at=u.created_at,
                test_password=hint,
                password_note=(
                    "shown (set via dev panel since API start)"
                    if hint
                    else "unknown — hash only in DB; use Set test password"
                ),
            )
        )
    return DevUserListResponse(
        warning=(
            "DEV ONLY. Real passwords cannot be read from the database (they are hashed). "
            "Use 'Set test password' to assign a known password for login tests."
        ),
        users=rows,
    )


@router.post("/users/set-password", response_model=SetTestPasswordResponse)
def set_test_password(
    body: SetTestPasswordRequest,
    db: Session = Depends(get_db),
):
    """Set a known password for a user (dev only) and return it for the UI list."""
    _require_dev_mode()
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    password = body.password or DEFAULT_TEST_PASSWORD
    user.hashed_password = hash_password(password)
    db.commit()
    _test_password_hints[email] = password

    return SetTestPasswordResponse(
        email=email,
        password=password,
        message="Password updated. You can log in with this password until you change it.",
    )


@router.post("/users/set-all-passwords", response_model=SetAllPasswordsResponse)
def set_all_test_passwords(
    password: str = DEFAULT_TEST_PASSWORD,
    db: Session = Depends(get_db),
):
    """Set the same test password for every user (dev only)."""
    _require_dev_mode()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="password min length 8")

    users = db.query(User).all()
    updated: list[str] = []
    for u in users:
        u.hashed_password = hash_password(password)
        _test_password_hints[u.email.lower()] = password
        updated.append(u.email)
    db.commit()

    return SetAllPasswordsResponse(
        password=password,
        updated=updated,
        message=f"Set password for {len(updated)} user(s) to the value returned in 'password'.",
    )
