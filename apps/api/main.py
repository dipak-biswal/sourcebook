from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
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
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
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


@app.on_event("startup")
def on_startup() -> None:
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
