import ipaddress

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "dev-only-change-me-sourcebook"


def _is_local_host(host: str) -> bool:
    """Loopback, private-range IPs, and bare/.local hostnames count as local."""
    h = (host or "").lower()
    if not h or h in ("localhost",) or h.endswith(".local") or "." not in h:
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def normalize_database_url(url: str) -> str:
    """Render/Neon often give postgresql://; SQLAlchemy needs +psycopg and SSL off-local."""
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql://") and not u.startswith("postgresql+"):
        u = "postgresql+psycopg://" + u[len("postgresql://") :]
    # typo / old local default without '+'
    if u.startswith("postgresql_psycopg://"):
        u = "postgresql+psycopg://" + u[len("postgresql_psycopg://") :]

    local = "127.0.0.1" in u or "localhost" in u
    if not local and "sslmode=" not in u:
        u = u + ("&" if "?" in u else "?") + "sslmode=require"
    return u


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Sourcebook"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://sourcebook:sourcebook@127.0.0.1:5432/sourcebook"
    )
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    upload_dir: str = "./data/uploads"

    # Embeddings
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    # Must match the pgvector column dimension (chunks.embedding); changing
    # the embedding model to one with different dims needs a migration.
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o-mini"
    visual_summary_model: str = "gpt-4o-mini"
    rag_top_k: int = 5
    # Cosine floor: below this → no hits, no sources (off-topic questions).
    # Raise (e.g. 0.25) if off-topic still retrieves; lower if on-topic misses.
    rag_min_score: float = 0.22

    # Local testing helpers (list users / set test passwords). NEVER enable in production.
    dev_mode: bool = True

    # Redis / RQ background ingest
    # Local Redis: redis://127.0.0.1:6379/0
    # Windows Docker host example: redis://192.168.31.50:6379/0
    redis_url: str = "redis://127.0.0.1:6379/0"
    ingest_use_queue: bool = True
    ingest_job_timeout_seconds: int = 600

    # Per-user rate limits (fixed window). 0 = unlimited for that scope.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_chat_per_window: int = 20
    rate_limit_ingest_per_window: int = 10
    rate_limit_agent_per_window: int = 10

    # Logging
    log_level: str = "INFO"
    log_json: bool = True  # false = human-readable lines for local terminals

    # Comma-separated browser origins allowed to call the API (CORS).
    # Override with CORS_ORIGINS on Render if you change the Vercel domain.
    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5174,http://localhost:5174,"
        "https://sourcebook-peach.vercel.app"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def is_local_database(self) -> bool:
        """A remote (public-host) database means we're not on a dev machine."""
        from sqlalchemy.engine import make_url

        return _is_local_host(make_url(self.sqlalchemy_database_url).host or "")


settings = Settings()
