"""read_document tool: pagination, truncation, and tenancy scoping."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.main.tools import build_tools
from app.db import Base
from app.models import Chunk, Document, User, Workspace


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


def _seed_document(db, ws_id, filename="doc.txt", chunk_count=3, status="ready"):
    doc = Document(
        workspace_id=ws_id,
        filename=filename,
        storage_key=f"{ws_id}/{filename}",
        status=status,
    )
    db.add(doc)
    db.flush()
    for i in range(chunk_count):
        db.add(
            Chunk(
                document_id=doc.id,
                workspace_id=ws_id,
                chunk_index=i,
                content=f"chunk-{i} text",
            )
        )
    db.commit()
    return doc


def _read_document_tool(db, ws_id, user_id):
    tools = build_tools(db, workspace_id=ws_id, user_id=user_id, agent_type="general")
    return next(t for t in tools if t.name == "read_document")


def test_read_document_returns_ordered_content(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()
    doc = _seed_document(db_session, ws.id)

    tool = _read_document_tool(db_session, ws.id, user.id)
    result = tool.invoke({"document_id": str(doc.id)})

    assert result["filename"] == "doc.txt"
    assert result["total_chunks"] == 3
    assert result["chunks_returned"] == 3
    assert result["has_more"] is False
    assert result["next_start_chunk"] is None
    assert result["content"].index("chunk-0") < result["content"].index("chunk-2")


def test_read_document_paginates(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()
    doc = _seed_document(db_session, ws.id, chunk_count=10)

    tool = _read_document_tool(db_session, ws.id, user.id)
    first = tool.invoke(
        {"document_id": str(doc.id), "start_chunk": 0, "max_chunks": 4}
    )
    assert first["chunks_returned"] == 4
    assert first["has_more"] is True
    assert first["next_start_chunk"] == 4
    assert "chunk-4" not in first["content"]

    second = tool.invoke(
        {"document_id": str(doc.id), "start_chunk": 4, "max_chunks": 4}
    )
    assert "chunk-4" in second["content"]
    assert second["next_start_chunk"] == 8


def test_read_document_clamps_max_chunks(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()
    doc = _seed_document(db_session, ws.id, chunk_count=15)

    tool = _read_document_tool(db_session, ws.id, user.id)
    result = tool.invoke({"document_id": str(doc.id), "max_chunks": 100})
    assert result["chunks_returned"] == 12  # clamped


def test_read_document_rejects_cross_workspace_access(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws_a = Workspace(name="A")
    ws_b = Workspace(name="B")
    db_session.add_all([user, ws_a, ws_b])
    db_session.flush()
    doc_b = _seed_document(db_session, ws_b.id)

    tool = _read_document_tool(db_session, ws_a.id, user.id)
    result = tool.invoke({"document_id": str(doc_b.id)})
    assert result == {"error": "document not found in this workspace"}


def test_read_document_invalid_uuid(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()

    tool = _read_document_tool(db_session, ws.id, user.id)
    assert tool.invoke({"document_id": "not-a-uuid"}) == {
        "error": "invalid document_id"
    }
    assert "error" in tool.invoke({"document_id": str(uuid.uuid4())})


def test_read_document_unignested_document_notes_status(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()
    doc = _seed_document(db_session, ws.id, chunk_count=0, status="processing")

    tool = _read_document_tool(db_session, ws.id, user.id)
    result = tool.invoke({"document_id": str(doc.id)})
    assert result["total_chunks"] == 0
    assert "not ingested yet" in result["note"]
