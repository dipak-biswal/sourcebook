"""RQ job functions for document ingest.

Run a worker (from apps/api):

    uv run rq worker sourcebook-ingest --url $REDIS_URL

Or:

    uv run python -m app.workers.rq_worker
"""

from __future__ import annotations

import uuid

from app.config import settings
from app.db import SessionLocal
from app.ingestion.parsers import ParseError
from app.ingestion.service import ingest_document_chunks
from app.logging_config import get_logger, log_extra, setup_logging
from app.models import Document

# Worker process may not import main.py — configure logs here.
setup_logging(level=settings.log_level, json_logs=settings.log_json)
logger = get_logger("sourcebook.worker.ingest")


def process_document_ingest(document_id: str) -> dict:
    """
    Background job: parse → chunk → embed for one document.

    Opens its own DB session (must not reuse the API request session).
    """
    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_uuid)
        if not doc:
            logger.warning(
                "document_not_found",
                extra=log_extra(event="ingest_missing", document_id=document_id),
            )
            return {"ok": False, "error": "document_not_found", "document_id": document_id}

        doc.status = "processing"
        doc.error = None
        db.commit()
        db.refresh(doc)
        logger.info(
            "ingest_processing",
            extra=log_extra(
                event="ingest_processing",
                document_id=document_id,
                workspace_id=str(doc.workspace_id),
            ),
        )

        try:
            rows = ingest_document_chunks(db, doc)
            logger.info(
                "ingest_ready",
                extra=log_extra(
                    event="ingest_ready",
                    document_id=document_id,
                    workspace_id=str(doc.workspace_id),
                ),
            )
            return {
                "ok": True,
                "document_id": document_id,
                "status": "ready",
                "chunks": len(rows),
            }
        except ParseError as e:
            doc.status = "failed"
            doc.error = str(e)
            db.commit()
            logger.warning(
                "ingest_parse_failed",
                extra=log_extra(
                    event="ingest_failed",
                    document_id=document_id,
                    workspace_id=str(doc.workspace_id),
                ),
            )
            return {
                "ok": False,
                "document_id": document_id,
                "status": "failed",
                "error": str(e),
            }
        except Exception as e:
            doc.status = "failed"
            doc.error = str(e)
            db.commit()
            logger.exception(
                "ingest_failed",
                extra=log_extra(
                    event="ingest_failed",
                    document_id=document_id,
                    workspace_id=str(doc.workspace_id),
                ),
            )
            # Re-raise so RQ marks the job failed (for retries / dead letter)
            raise
    finally:
        db.close()
