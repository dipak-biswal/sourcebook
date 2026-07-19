"""Document viewer chunk endpoints (citation deep-links)."""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import get_current_user
from app.models import Chunk, Document, User, Workspace, WorkspaceMember
from app.security import hash_password
from main import app


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_list_chunks_and_get_chunk_scoped_to_member():
    db = _session()
    user = User(
        id=uuid.uuid4(),
        email="viewer@example.com",
        hashed_password=hash_password("password123"),
    )
    other = User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password=hash_password("password123"),
    )
    ws = Workspace(id=uuid.uuid4(), name="Docs WS")
    db.add_all([user, other, ws])
    db.add(WorkspaceMember(user_id=user.id, workspace_id=ws.id, role="owner"))
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        filename="guide.md",
        content_type="text/markdown",
        storage_key=f"{ws.id}/guide.md",
        status="ready",
        created_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    c0 = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        workspace_id=ws.id,
        chunk_index=0,
        content="First chunk about distributed systems.",
        token_count=8,
    )
    c1 = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        workspace_id=ws.id,
        chunk_index=1,
        content="Second chunk about CAP tradeoffs.",
        token_count=7,
    )
    db.add_all([c0, c1])
    db.commit()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    listed = client.get(f"/documents/{doc.id}/chunks")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 2
    assert body[0]["chunk_index"] == 0
    assert "distributed" in body[0]["content"]

    got = client.get(f"/documents/chunks/{c1.id}")
    assert got.status_code == 200
    detail = got.json()
    assert detail["filename"] == "guide.md"
    assert detail["document_id"] == str(doc.id)
    assert "CAP" in detail["content"]

    meta = client.get(f"/documents/{doc.id}")
    assert meta.status_code == 200
    assert meta.json()["filename"] == "guide.md"

    # Non-member cannot read
    app.dependency_overrides[get_current_user] = lambda: other
    denied = client.get(f"/documents/{doc.id}/chunks")
    assert denied.status_code == 403

    app.dependency_overrides.clear()
    db.close()
