"""RQ job functions for document ingest.

Run a worker (from apps/api):

    uv run rq worker sourcebook-ingest --url $REDIS_URL

Or:

    uv run python -m app.workers.rq_worker
"""

from __future__ import annotations

import uuid

from app.db import SessionLocal
from app.ingestion.parsers import ParseError
from app.ingestion.service import ingest_document_chunks
from app.models import Document


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
            return {"ok": False, "error": "document_not_found", "document_id": document_id}

        doc.status = "processing"
        doc.error = None
        db.commit()
        db.refresh(doc)

        try:
            rows = ingest_document_chunks(db, doc)
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
            # Re-raise so RQ marks the job failed (for retries / dead letter)
            raise
    finally:
        db.close()
