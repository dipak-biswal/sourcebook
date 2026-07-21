"""Grace-turn recovery from repeated tool calls in the agent loop."""

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.agents.main.runner.finalize as finalize_mod
import app.agents.main.runner.loop as loop_mod
from app.agents.main.runner.loop import _run_tool_loop
from app.db import Base
from app.models import AgentRun, User, Workspace

DUP_MARKER = "duplicate of an earlier call"


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
def run_env(db_session, monkeypatch):
    """Seed a run and stub every LLM touchpoint; returns a loop driver."""
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="W")
    db_session.add_all([user, ws])
    db_session.flush()
    run = AgentRun(
        workspace_id=ws.id,
        user_id=user.id,
        goal="test goal",
        status="running",
        agent_type="general",
    )
    db_session.add(run)
    db_session.commit()

    monkeypatch.setattr(loop_mod, "_llm", lambda model: MagicMock())
    monkeypatch.setattr(finalize_mod, "_synthesize_final_answer", lambda *a, **k: None)
    monkeypatch.setattr(finalize_mod, "should_offer_presentation", lambda **k: False)
    # search_documents runs in a thread pool — keep it off the sqlite session.
    monkeypatch.setattr("app.agents.main.tools.factory.retrieve_chunks", lambda *a, **k: [])

    events: list[tuple[str, dict]] = []

    def drive(turns, messages=None):
        script = iter(turns)

        def fake_invoke(model, msgs, **kwargs):
            return next(script), 1.0

        monkeypatch.setattr(loop_mod, "_invoke_llm_turn", fake_invoke)
        return _run_tool_loop(
            db_session,
            run,
            messages=messages
            or [SystemMessage(content="sys"), HumanMessage(content="goal")],
            max_steps=8,
            on_event=lambda kind, payload: events.append((kind, payload)),
        )

    return run, drive, events


def _search_call(call_id, query="q1"):
    return {
        "name": "search_documents",
        "args": {"query": query},
        "id": call_id,
        "type": "tool_call",
    }


def _dup_tool_messages(run, db_session):
    # dup notices are persisted as tool_result steps carrying the marker
    return [
        s
        for s in run.steps
        if s.type == "tool_result" and DUP_MARKER in json.dumps(s.output or {})
    ]


def test_first_duplicate_gets_grace_second_breaks(run_env, db_session):
    run, drive, events = run_env
    result = drive(
        [
            AIMessage(content="", tool_calls=[_search_call("c1")]),
            AIMessage(content="", tool_calls=[_search_call("c2")]),
            AIMessage(content="", tool_calls=[_search_call("c3")]),
        ]
    )

    assert result.status == "completed"
    warnings = [p["message"] for k, p in events if k == "loop_warning"]
    assert len(warnings) == 2
    assert "continuing" in warnings[0]
    assert "breaking loop" in warnings[1]
    dup_steps = _dup_tool_messages(run, db_session)
    assert len(dup_steps) == 1  # only c2 got the notice; c3 hard-exited


def test_mixed_turn_executes_novel_call(run_env, db_session):
    run, drive, events = run_env
    final_text = (
        "Here is a substantive final answer with plenty of grounded detail "
        "about the goal so it is not considered weak."
    )
    result = drive(
        [
            AIMessage(content="", tool_calls=[_search_call("c1", "q1")]),
            AIMessage(
                content="",
                tool_calls=[_search_call("c2", "q1"), _search_call("c3", "q2")],
            ),
            AIMessage(content=final_text, tool_calls=[]),
        ]
    )

    assert result.status == "completed"
    assert result.final_answer == final_text
    # c2 (duplicate) got the notice, c3 (novel) got a real execution
    dup_steps = _dup_tool_messages(run, db_session)
    assert len(dup_steps) == 1
    executed_queries = [
        s.input.get("query")
        for s in run.steps
        if s.type == "tool_result"
        and s.tool_name == "search_documents"
        and DUP_MARKER not in json.dumps(s.output or {})
    ]
    assert "q2" in executed_queries


def test_duplicate_write_does_not_pause_for_approval(run_env, db_session):
    run, drive, events = run_env
    note_args = {"title": "T", "body": "B"}
    prior = [
        SystemMessage(content="sys"),
        HumanMessage(content="goal"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "create_note", "args": note_args, "id": "w0", "type": "tool_call"}
            ],
        ),
        ToolMessage(
            content=json.dumps({"id": "n1", "status": "created"}),
            tool_call_id="w0",
            name="create_note",
        ),
    ]
    final_text = (
        "The note already exists, so here is the wrap-up answer with enough "
        "detail to stand on its own."
    )
    result = drive(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "create_note", "args": note_args, "id": "w1", "type": "tool_call"}
                ],
            ),
            AIMessage(content=final_text, tool_calls=[]),
        ],
        messages=prior,
    )

    # seen_calls is seeded from prior AIMessages, so the repeat is caught,
    # answered with a notice, and never pauses for approval.
    assert result.status == "completed"
    assert result.pending_tool is None
    assert result.final_answer == final_text
    assert len(_dup_tool_messages(run, db_session)) == 1
