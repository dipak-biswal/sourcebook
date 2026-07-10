import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.ingestion.parsers import ParseError
from app.ingestion.service import ingest_document_chunks
from app.models import Document, User, WorkspaceMember
from app.schemas import DocumentResponse


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
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Docuemnt not found"
        )

    _require_workspace_member(db, current_user.id, doc.workspace_id)

    try:
        doc.status = "processing"
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
