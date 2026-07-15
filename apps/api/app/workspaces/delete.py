import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.storage import get_storage
from app.models import (
    AgentRun,
    AgentStep,
    Chunk,
    Conversation,
    Document,
    Message,
    Note,
    UsageEvent,
    Workspace,
    WorkspaceMember,
)


def purge_workspace(db: Session, workspace_id: uuid.UUID) -> None:
    """Delete all rows and files for a workspace (explicit cascade)."""
    conv_ids = select(Conversation.id).where(Conversation.workspace_id == workspace_id)
    db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
    db.execute(delete(Conversation).where(Conversation.workspace_id == workspace_id))

    run_ids = select(AgentRun.id).where(AgentRun.workspace_id == workspace_id)
    db.execute(delete(AgentStep).where(AgentStep.run_id.in_(run_ids)))
    db.execute(delete(AgentRun).where(AgentRun.workspace_id == workspace_id))

    db.execute(delete(Chunk).where(Chunk.workspace_id == workspace_id))

    docs = db.scalars(
        select(Document).where(Document.workspace_id == workspace_id)
    ).all()
    storage = get_storage()
    for doc in docs:
        storage.delete(doc.storage_key)
    db.execute(delete(Document).where(Document.workspace_id == workspace_id))

    db.execute(delete(Note).where(Note.workspace_id == workspace_id))
    db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    db.execute(
        update(UsageEvent)
        .where(UsageEvent.workspace_id == workspace_id)
        .values(workspace_id=None)
    )

    # Local backend keeps per-workspace dirs on disk; clear leftovers
    ws_dir = Path(settings.upload_dir) / str(workspace_id)
    if ws_dir.is_dir():
        shutil.rmtree(ws_dir, ignore_errors=True)

    workspace = db.get(Workspace, workspace_id)
    if workspace:
        db.delete(workspace)