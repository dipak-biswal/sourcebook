"""Auth token minting / refresh helpers."""

from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.security import create_access_token, decode_access_token


def test_create_access_token_round_trip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_create_access_token_has_future_exp():
    token = create_access_token("user-123")
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert exp > datetime.now(timezone.utc) + timedelta(minutes=60)


def test_decode_rejects_tampered_token():
    token = create_access_token("user-123")
    bad = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert decode_access_token(bad) is None
