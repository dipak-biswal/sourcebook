import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Note, User, WorkspaceMember
from app.schemas import NoteCreateRequest, NoteUpdateRequest

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


def _require_member(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    ok = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )


@router.get("", response_model=list[NoteResponse])
def list_notes(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_member(db, current_user.id, workspace_id)
    return (
        db.query(Note)
        .filter(Note.workspace_id == workspace_id)
        .order_by(Note.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    body: NoteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_member(db, current_user.id, body.workspace_id)
    note = Note(
        workspace_id=body.workspace_id,
        user_id=current_user.id,
        title=body.title.strip(),
        body=body.body,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    _require_member(db, current_user.id, note.workspace_id)
    return note


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: uuid.UUID,
    body: NoteUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    _require_member(db, current_user.id, note.workspace_id)
    if body.title is not None:
        note.title = body.title
    if body.body is not None:
        note.body = body.body
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    _require_member(db, current_user.id, note.workspace_id)
    db.delete(note)
    db.commit()
    return None
