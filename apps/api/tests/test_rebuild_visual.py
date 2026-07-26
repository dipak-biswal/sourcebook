"""Rebuild visual summary for completed runs."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.main.runner.lifecycle import rebuild_visual_summary
from app.db import Base
from app.models import AgentRun, User, Workspace


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


@pytest.fixture
def completed_run(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="Learn System Design")
    db_session.add_all([user, ws])
    db_session.flush()
    run = AgentRun(
        workspace_id=ws.id,
        user_id=user.id,
        goal="Create a complete study sheet for Outbox",
        status="completed",
        agent_type="general",
        final_answer=(
            "## 1. Why\n- Atomicity\n\n## 2. Flow\nA → B → C\n\n"
            "## 3. Practices\n- Index status\n- Idempotent consumers\n"
        ),
        presentation_spec={
            "type": "generative_ui",
            "title": "Old",
            "blocks": [],
            "early_visual": True,
        },
        run_options={"enabled_mcp_ids": []},
    )
    db_session.add(run)
    db_session.commit()
    return run


def test_rebuild_rejects_running(db_session, completed_run):
    completed_run.status = "running"
    db_session.commit()
    with pytest.raises(ValueError, match="completed"):
        rebuild_visual_summary(db_session, completed_run)


def test_rebuild_rejects_short_answer(db_session, completed_run):
    completed_run.final_answer = "too short"
    db_session.commit()
    with pytest.raises(ValueError, match="no substantive answer"):
        rebuild_visual_summary(db_session, completed_run)


def test_rebuild_clears_spec_and_calls_visual(db_session, completed_run):
    def fake_visual(db, run, *, step_index, on_event=None, trace_live=None):
        run.presentation_spec = {
            "type": "generative_ui",
            "title": "Rebuilt",
            "blocks": [{"type": "key_points", "items": ["a", "b"]}],
            "status": "complete",
        }
        run.status = "completed"
        db.commit()
        return run

    with patch(
        "app.agents.main.runner.lifecycle._run_visual_summary_agent",
        side_effect=fake_visual,
    ):
        result = rebuild_visual_summary(db_session, completed_run)

    assert result.status == "completed"
    assert result.presentation_spec
    assert result.presentation_spec.get("title") == "Rebuilt"
