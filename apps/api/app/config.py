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

    # S3-compatible object storage (R2 / B2 / S3). Setting S3_ENDPOINT_URL
    # switches document storage from local disk to the bucket.
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""

    # Embeddings
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    # Must match the pgvector column dimension (chunks.embedding); changing
    # the embedding model to one with different dims needs a migration.
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o-mini"
    visual_summary_model: str = "gpt-4o-mini"
    # When True, the layout planner LLM decides block selection/order/width;
    # code skeleton is fallback. Set False to force skeleton-first instantly.
    visual_summary_llm_planner: bool = True
    # When True, structured facts for the visual summary come from an LLM
    # extraction over the answer + evidence (full visual schema: levels,
    # matrix_rows, metrics, …). The regex extractor remains the fallback.
    visual_summary_llm_extractor: bool = True
    # When True, workspace context (tone/outcome/affordances/planner example)
    # is derived by an LLM profiler and cached on the workspace row; the
    # keyword heuristic remains the fallback. One call per workspace change.
    workspace_llm_profiler: bool = True
    # When True, the Visual Summary phase runs through the legacy LLM tool
    # loop (an agent decides when to call plan_layout/render_ui). Default is
    # the code orchestrator, which runs plan → render directly with no outer
    # agent turns — same steps and trace, fewer LLM calls.
    visual_summary_agent_loop: bool = False
    # When True (and both extractor + planner flags are on), extraction and
    # layout planning happen in ONE combined LLM call instead of two. The
    # regex heuristic still gates handoff validation; a thin heuristic falls
    # back to a separate extraction call. Set False to restore two calls.
    visual_summary_combined_call: bool = True
    rag_top_k: int = 5
    # Cosine floor: below this → no hits, no sources (off-topic questions).
    # Raise (e.g. 0.25) if off-topic still retrieves; lower if on-topic misses.
    rag_min_score: float = 0.22
    # Hybrid retrieval (vector + full-text, fused with Reciprocal Rank Fusion).
    rag_candidate_k: int = 20  # per-arm candidate pool before fusion
    rag_rrf_k: int = 60  # RRF constant; higher = flatter rank weighting
    # Keyword-arm relevance floor for the denial gate. A query is denied only
    # when max cosine < rag_min_score AND no keyword row beats this ts_rank.
    # Raise slightly (e.g. 0.02) if common single-word matches leak through.
    rag_keyword_min_rank: float = 0.0
    # LLM reranking: fuse to a wider pool, then an LLM scores candidates down
    # to rag_top_k. Runs after the denial gate (off-topic behavior unchanged).
    rag_rerank_enabled: bool = True
    rag_rerank_model: str = ""  # empty → falls back to chat_model
    rag_rerank_candidate_k: int = 12  # pool size fused before rerank (≥ rag_top_k)

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
