import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Document, User, WorkspaceMember
from app.schemas import DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


def _require_workspce_member(
    db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> WorkspaceMember:
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
    return member


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_workspce_member(db, current_user.id, workspace_id)

    docs = (
        db.query(Document)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    return docs


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID = Form(...),
    file: UploadFile = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_workspce_member(db, current_user.id, workspace_id)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename"
        )

    doc_id = uuid.uuid4()
    safe_name = Path(file.filename).name
    rel_key = f"{workspace_id}/{doc_id}_{safe_name}"
    dest_dir = Path(settings.upload_dir) / str(workspace_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{doc_id}_{safe_name}"

    content = await file.read()
    dest_path.write_bytes(content)

    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        filename=safe_name,
        content_type=file.content_type,
        storage_key=rel_key,
        status="Uploaded",
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    _require_workspce_member(db, current_user.id, doc.workspace_id)

    path = Path(settings.upload_dir) / doc.storage_key

    if path.is_file():
        path.unlink()

    db.delete(doc)
    db.commit()

    return None
