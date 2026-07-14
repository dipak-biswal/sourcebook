from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import Base, engine
from app.logging_config import get_logger, setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routers import (
    agents,
    auth,
    chat,
    documents,
    dev,
    health,
    ingest,
    notes,
    usage,
    workspaces,
)

# Register models on Base.metadata before create_all
import app.models  # noqa: F401

setup_logging(level=settings.log_level, json_logs=settings.log_json)
logger = get_logger("sourcebook.api")

app = FastAPI(
    title="Sourcebook",
    description="Multi-tenant document AI workspace",
    version="0.1.0",
)

# Order: last added = outermost. RequestLogging wraps CORS + routes.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON so deploy issues are visible (and CORS middleware can attach headers)."""
    logger.exception(
        "unhandled_exception",
        extra={"event": "unhandled_exception", "path": str(request.url.path)},
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        },
    )

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(usage.router)
app.include_router(agents.router)
app.include_router(notes.router)
if settings.dev_mode:
    app.include_router(dev.router)


def _ensure_column(table: str, column: str, ddl: str) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column in cols:
        return
    with engine.begin() as conn:
        conn.execute(text(ddl))
    logger.info(
        "db_column_added",
        extra={"event": "db_migrate", "table": table, "column": column},
    )


def _run_schema_migrations() -> None:
    """Lightweight migrations for DBs created before newer columns."""
    _ensure_column(
        "agent_runs",
        "agent_type",
        "ALTER TABLE agent_runs "
        "ADD COLUMN agent_type VARCHAR(32) NOT NULL DEFAULT 'general'",
    )
    _ensure_column(
        "agent_runs",
        "presentation_spec",
        "ALTER TABLE agent_runs ADD COLUMN presentation_spec JSON",
    )
    _ensure_column(
        "workspaces",
        "description",
        "ALTER TABLE workspaces ADD COLUMN description TEXT",
    )
    _ensure_column(
        "workspaces",
        "tags",
        "ALTER TABLE workspaces ADD COLUMN tags JSON",
    )

    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "agent_runs" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("agent_runs")}
        if "agent_type" in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agent_runs_agent_type "
                        "ON agent_runs (agent_type)"
                    )
                )


@app.on_event("startup")
def on_startup() -> None:
    # Fresh cloud DBs need tables; local already has them (create_all is idempotent).
    try:
        Base.metadata.create_all(bind=engine)
        _run_schema_migrations()
        logger.info("db_tables_ready", extra={"event": "db_init"})
    except Exception:
        logger.exception("db_init_failed", extra={"event": "db_init_failed"})
        raise

    logger.info(
        "api_started",
        extra={
            "event": "startup",
            "app": settings.app_name,
            "dev_mode": settings.dev_mode,
            "ingest_use_queue": settings.ingest_use_queue,
            "log_json": settings.log_json,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.api_host, port=settings.api_port, reload=True)
