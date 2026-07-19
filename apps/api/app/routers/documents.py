import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.ingestion.parsers import is_supported_filename, supported_types_message
from app.models import Chunk, Document, User, WorkspaceMember
from app.schemas import ChunkDetailResponse, ChunkResponse, DocumentResponse
from app.storage import get_storage

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

    safe_name = Path(file.filename).name
    if not is_supported_filename(safe_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. {supported_types_message()}",
        )

    doc_id = uuid.uuid4()
    rel_key = f"{workspace_id}/{doc_id}_{safe_name}"

    content = await file.read()
    get_storage().save(rel_key, content)

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


# Static path must be registered before /{document_id} so "chunks" is not
# parsed as a UUID document id.
@router.get("/chunks/{chunk_id}", response_model=ChunkDetailResponse)
def get_chunk(
    chunk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resolve a single chunk (with filename) for citation navigation."""
    ch = db.get(Chunk, chunk_id)
    if not ch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )
    _require_workspce_member(db, current_user.id, ch.workspace_id)
    doc = db.get(Document, ch.document_id)
    return ChunkDetailResponse(
        id=ch.id,
        document_id=ch.document_id,
        workspace_id=ch.workspace_id,
        chunk_index=ch.chunk_index,
        content=ch.content,
        token_count=ch.token_count,
        filename=doc.filename if doc else None,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
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
    return doc


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
def list_document_chunks(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ordered text chunks for the document viewer / citation deep-links."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    _require_workspce_member(db, current_user.id, doc.workspace_id)
    return (
        db.query(Chunk)
        .filter(Chunk.document_id == doc.id, Chunk.workspace_id == doc.workspace_id)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )


@router.delete("/{document_id}")
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

    get_storage().delete(doc.storage_key)

    # Delete chunks first so SQLAlchemy does not NULL out document_id
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete(
        synchronize_session=False
    )
    db.delete(doc)
    db.commit()

    return None
