import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger, log_extra
from app.models import Document, User, WorkspaceMember
from app.rate_limit import rate_limit
from app.schemas import DocumentResponse
from app.workers.ingest_jobs import process_document_ingest
from app.workers.queue import (
    enqueue_document_ingest,
    ingest_worker_count,
    redis_ping,
)

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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("ingest")),
):
    """
    Start document ingest: parse → chunk → embed.

    - INGEST_USE_QUEUE=true: enqueue RQ job (needs Redis + worker; worker must see files).
    - INGEST_USE_QUEUE=false: FastAPI BackgroundTasks on this process (good for single
      Render web service; avoids gateway 502 from long embedding requests).
    - Queue on but no worker listening: fall back to in-process ingest instead of
      leaving the document stuck in 'queued'.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    _require_workspace_member(db, current_user.id, doc.workspace_id)

    # --- RQ queue path ---
    use_queue = settings.ingest_use_queue
    if use_queue:
        if not redis_ping():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Redis unavailable for background ingest. "
                    "Start Redis and the RQ worker, "
                    "or set INGEST_USE_QUEUE=false for in-process background ingest."
                ),
            )
        if ingest_worker_count() == 0:
            # Redis is up but nobody is consuming the queue (e.g. API-only
            # deploy) — enqueueing would strand the document in 'queued'.
            use_queue = False
            logger.warning(
                "ingest_no_worker_fallback",
                extra=log_extra(
                    event="ingest_no_worker_fallback",
                    document_id=str(doc.id),
                    workspace_id=str(doc.workspace_id),
                ),
            )
    if use_queue:
        try:
            doc.status = "queued"
            doc.error = None
            db.commit()
            db.refresh(doc)
            job = enqueue_document_ingest(doc.id, current_user.id)
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

    # --- In-process background (single-instance deploy; avoids proxy timeouts) ---
    doc.status = "processing"
    doc.error = None
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(process_document_ingest, str(doc.id), str(current_user.id))
    logger.info(
        "ingest_scheduled_local",
        extra=log_extra(
            event="ingest_scheduled_local",
            document_id=str(doc.id),
            workspace_id=str(doc.workspace_id),
        ),
    )
    return doc
