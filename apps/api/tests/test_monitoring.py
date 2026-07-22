"""Monitoring overview — online/active user counts."""

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.deps import user_is_admin
from app.models import User
from app.routers.monitoring import monitoring_users


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def _user(
    email: str,
    *,
    last_seen=None,
    last_login=None,
    created=None,
) -> User:
    u = User(
        email=email,
        hashed_password="x",
    )
    u.id = __import__("uuid").uuid4()
    u.created_at = created or datetime.now(timezone.utc) - timedelta(days=10)
    u.last_seen_at = last_seen
    u.last_login_at = last_login
    return u


def test_monitoring_counts_online_and_active(monkeypatch):
    monkeypatch.setattr(settings, "monitoring_online_minutes", 15)
    now = datetime.now(timezone.utc)
    rows = [
        _user("online@example.com", last_seen=now - timedelta(minutes=2)),
        _user(
            "today@example.com",
            last_seen=now - timedelta(hours=3),
            last_login=now - timedelta(hours=4),
        ),
        _user(
            "week@example.com",
            last_login=now - timedelta(days=3),
        ),
        _user("stale@example.com", last_login=now - timedelta(days=30)),
    ]
    db = _FakeDB(rows)
    admin = rows[0]
    result = monitoring_users(current_user=admin, db=db)
    assert result.total_users == 4
    assert result.online_now == 1
    assert result.active_today == 2  # online + today
    assert result.active_7d == 3  # + week
    assert result.users[0].online is True
    assert result.users[0].email == "online@example.com"


def test_user_is_admin_open_when_empty(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")
    u = _user("anyone@example.com")
    assert user_is_admin(u) is True


def test_user_is_admin_restricted(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "owner@example.com, ops@x.com")
    assert user_is_admin(_user("owner@example.com")) is True
    assert user_is_admin(_user("other@example.com")) is False
