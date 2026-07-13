import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AgentRun,
    AgentStep,
    Chunk,
    Conversation,
    Document,
    Message,
    Note,
    User,
    Workspace,
    WorkspaceMember,
)
from app.workspaces.delete import purge_workspace


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_purge_workspace_deletes_related_rows(db_session):
    user = User(email="owner@example.com", hashed_password="x")
    ws = Workspace(name="To delete")
    db_session.add_all([user, ws])
    db_session.flush()

    db_session.add(WorkspaceMember(user_id=user.id, workspace_id=ws.id, role="owner"))

    doc = Document(
        workspace_id=ws.id,
        filename="a.txt",
        storage_key=f"{ws.id}/doc.txt",
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()

    db_session.add(
        Chunk(
            document_id=doc.id,
            workspace_id=ws.id,
            chunk_index=0,
            content="hello",
        )
    )

    conv = Conversation(workspace_id=ws.id, user_id=user.id, title="Chat")
    db_session.add(conv)
    db_session.flush()

    db_session.add(
        Message(conversation_id=conv.id, role="user", content="hi")
    )

    run = AgentRun(workspace_id=ws.id, user_id=user.id, goal="test", status="completed")
    db_session.add(run)
    db_session.flush()

    db_session.add(
        AgentStep(run_id=run.id, step_index=0, type="tool_result", tool_name="list")
    )
    db_session.add(Note(workspace_id=ws.id, user_id=user.id, title="N", body="b"))
    db_session.commit()

    ws_id = ws.id
    purge_workspace(db_session, ws_id)
    db_session.commit()

    assert db_session.get(Workspace, ws_id) is None
    assert db_session.query(Document).filter(Document.workspace_id == ws_id).count() == 0
    assert db_session.query(Chunk).filter(Chunk.workspace_id == ws_id).count() == 0
    assert db_session.query(Conversation).filter(Conversation.workspace_id == ws_id).count() == 0
    assert db_session.query(Message).count() == 0
    assert db_session.query(AgentRun).filter(AgentRun.workspace_id == ws_id).count() == 0
    assert db_session.query(AgentStep).count() == 0
    assert db_session.query(Note).filter(Note.workspace_id == ws_id).count() == 0
    assert (
        db_session.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == ws_id)
        .count()
        == 0
    )