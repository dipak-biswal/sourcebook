from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Sourcebook"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = (
        "postgresql_psycopg://sourcebook:sourcebook@127.0.0.1:5432/sourcebook"
    )
    jwt_secret: str = "dev-only-change-me-sourcebook"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    upload_dir: str = "./data/uploads"

    # Embeddings
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    rag_top_k: int = 5
    # Cosine floor: below this → no hits, no sources (off-topic questions).
    # Raise (e.g. 0.25) if off-topic still retrieves; lower if on-topic misses.
    rag_min_score: float = 0.22

    # Local testing helpers (list users / set test passwords). NEVER enable in production.
    dev_mode: bool = True


settings = Settings()
