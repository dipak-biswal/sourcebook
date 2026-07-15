from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import engine
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

# Register models on Base.metadata (Alembic autogenerate + tests rely on this)
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


def _run_db_migrations() -> None:
    """Bring the schema to head with Alembic.

    Databases created before Alembic (via create_all) have no alembic_version
    table but do have the baseline schema — stamp them at the baseline
    revision so only newer migrations run.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    api_dir = Path(__file__).resolve().parent
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))

    insp = inspect(engine)
    tables = insp.get_table_names()
    if "alembic_version" not in tables and "users" in tables:
        command.stamp(cfg, "001")
        logger.info("db_stamped_baseline", extra={"event": "db_migrate"})

    command.upgrade(cfg, "head")


@app.on_event("startup")
def on_startup() -> None:
    try:
        _run_db_migrations()
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
