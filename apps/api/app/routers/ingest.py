import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.ingestion.parsers import ParseError
from app.ingestion.service import ingest_document_chunks
from app.logging_config import get_logger, log_extra
from app.models import Document, User, WorkspaceMember
from app.rate_limit import rate_limit
from app.schemas import DocumentResponse
from app.workers.queue import enqueue_document_ingest, redis_ping

logger = get_logger("sourcebook.ingest")

router = APIRouter(prefix="/documents", tags=["ingest"])


def _require_workspace_member(
    db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )


@router.post("/{document_id}/ingest", response_model=DocumentResponse)
def ingest_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("ingest")),
):
    """
    Queue (or run) document ingest: parse → chunk → embed.

    When ingest_use_queue=True and Redis is up, returns quickly with status=queued
    and a background RQ worker performs the heavy work.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    _require_workspace_member(db, current_user.id, doc.workspace_id)

    # --- Background path (preferred) ---
    if settings.ingest_use_queue:
        if not redis_ping():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Redis unavailable for background ingest. "
                    "Start Redis (docker compose up -d redis) and the RQ worker: "
                    "uv run python -m app.workers.rq_worker. "
                    "Or set INGEST_USE_QUEUE=false for sync ingest."
                ),
            )
        try:
            doc.status = "queued"
            doc.error = None
            db.commit()
            db.refresh(doc)
            job = enqueue_document_ingest(doc.id)
            logger.info(
                "ingest_queued",
                extra=log_extra(
                    event="ingest_queued",
                    document_id=str(doc.id),
                    job_id=job.id,
                    workspace_id=str(doc.workspace_id),
                ),
            )
            return doc
        except HTTPException:
            raise
        except Exception as e:
            doc.status = "failed"
            doc.error = f"Failed to enqueue: {e}"
            db.commit()
            db.refresh(doc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=doc.error,
            ) from e

    # --- Sync fallback (dev without worker) ---
    try:
        doc.status = "processing"
        doc.error = None
        db.commit()
        db.refresh(doc)
        ingest_document_chunks(db, doc)
    except ParseError as e:
        doc.status = "failed"
        doc.error = str(e)
        db.commit()
        db.refresh(doc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        doc.status = "failed"
        doc.error = str(e)
        db.commit()
        db.refresh(doc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingest failed: {e}",
        ) from e

    db.refresh(doc)
    return doc
