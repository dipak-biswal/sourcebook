import pytest

from app.config import DEFAULT_JWT_SECRET, _is_local_host, settings
from main import _enforce_prod_safety


@pytest.mark.parametrize(
    "host,expected",
    [
        ("localhost", True),
        ("127.0.0.1", True),
        ("192.168.31.50", True),
        ("10.0.0.5", True),
        ("172.16.4.2", True),
        ("mybox.local", True),
        ("postgres", True),  # bare docker-compose service name
        ("8.8.8.8", False),
        ("dpg-abc123-a.oregon-postgres.render.com", False),
        ("ep-cool-name-123.us-east-2.aws.neon.tech", False),
    ],
)
def test_is_local_host(host, expected):
    assert _is_local_host(host) is expected


REMOTE_URL = "postgresql+psycopg://u:p@dpg-abc.oregon-postgres.render.com/db"
LOCAL_URL = "postgresql+psycopg://u:p@127.0.0.1:5432/db"


def _configure(monkeypatch, *, database_url, dev_mode, jwt_secret):
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "dev_mode", dev_mode)
    monkeypatch.setattr(settings, "jwt_secret", jwt_secret)


def test_remote_db_with_dev_mode_refuses_boot(monkeypatch):
    _configure(
        monkeypatch, database_url=REMOTE_URL, dev_mode=True, jwt_secret="x" * 40
    )
    with pytest.raises(RuntimeError, match="DEV_MODE"):
        _enforce_prod_safety()


def test_remote_db_with_default_jwt_secret_refuses_boot(monkeypatch):
    _configure(
        monkeypatch,
        database_url=REMOTE_URL,
        dev_mode=False,
        jwt_secret=DEFAULT_JWT_SECRET,
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _enforce_prod_safety()


def test_remote_db_with_secure_settings_boots(monkeypatch):
    _configure(
        monkeypatch, database_url=REMOTE_URL, dev_mode=False, jwt_secret="x" * 40
    )
    _enforce_prod_safety()


def test_local_db_allows_dev_defaults(monkeypatch):
    _configure(
        monkeypatch,
        database_url=LOCAL_URL,
        dev_mode=True,
        jwt_secret=DEFAULT_JWT_SECRET,
    )
    _enforce_prod_safety()
