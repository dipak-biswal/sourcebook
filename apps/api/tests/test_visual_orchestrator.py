"""Code orchestrator for the Visual Summary phase (no outer agent loop)."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.agents.visual_tools as visual_tools_mod
from app.agents.runner.lifecycle import _run_visual_summary_agent
from app.agents.runner.visual import _run_visual_pipeline
from app.agents.visual_tools import build_visual_tools
from app.config import settings
from app.db import Base
from app.models import AgentRun, AgentStep, User, Workspace
from app.presentation.context import PresentationContext
from app.presentation.evidence import AgentEvidenceBundle

FINAL_ANSWER = (
    "React and FastAPI are the core stack; RAG search shipped this quarter.\n\n"
    "- Shipped RAG features across workspaces\n"
    "- TypeScript frontend and Python API\n"
    "- Postgres with pgvector for retrieval\n"
)


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
def seeded_run(db_session):
    user = User(email="u@example.com", hashed_password="x")
    ws = Workspace(name="Engineering")
    db_session.add_all([user, ws])
    db_session.flush()
    run = AgentRun(
        workspace_id=ws.id,
        user_id=user.id,
        goal="Summarize the workspace",
        status="running",
        agent_type="general",
        final_answer=FINAL_ANSWER,
    )
    db_session.add(run)
    db_session.commit()
    return run


def _ctx(run: AgentRun) -> PresentationContext:
    return PresentationContext(
        workspace_id=run.workspace_id,
        user_id=run.user_id,
        goal=run.goal or "",
        final_answer=run.final_answer or "",
        workspace_name="Engineering",
        structured_content={
            "summary": "React and FastAPI are the core stack; RAG shipped.",
            "key_points": ["Shipped RAG features", "TypeScript and Python"],
            "faq": [{"question": "What stack?", "answer": "React + FastAPI"}],
            "themes": ["rag", "stack"],
            "sections": [],
        },
        agent_evidence=AgentEvidenceBundle(),
    )


def _steps(db_session, run) -> list[AgentStep]:
    return sorted(
        db_session.query(AgentStep).filter(AgentStep.run_id == run.id).all(),
        key=lambda s: s.step_index,
    )


def test_pipeline_plans_and_renders_without_agent_turns(
    db_session, seeded_run, monkeypatch
):
    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)

    events: list[tuple[str, dict]] = []
    result = _run_visual_pipeline(
        db_session,
        seeded_run,
        ctx=_ctx(seeded_run),
        step_index=0,
        on_event=lambda kind, payload: events.append((kind, payload)),
    )

    assert result.status == "completed"
    spec = result.presentation_spec
    assert isinstance(spec, dict) and spec.get("type") == "generative_ui"
    assert spec.get("blocks")

    steps = _steps(db_session, seeded_run)
    by_type = [(s.type, s.tool_name) for s in steps]
    assert ("tool_call", "plan_layout") in by_type
    assert ("tool_result", "plan_layout") in by_type
    assert ("tool_call", "render_ui") in by_type
    assert ("tool_result", "render_ui") in by_type
    assert any(s.type == "presentation" for s in steps)
    # No outer agent LLM turns
    assert not any(s.type in ("thought", "final") for s in steps)

    render_result = next(
        s for s in steps if s.type == "tool_result" and s.tool_name == "render_ui"
    )
    assert render_result.output.get("status") == "rendered"
    assert render_result.output.get("block_count", 0) >= 1


def test_pipeline_emits_presentation_skeleton_event(
    db_session, seeded_run, monkeypatch
):
    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)

    events: list[tuple[str, dict]] = []
    _run_visual_pipeline(
        db_session,
        seeded_run,
        ctx=_ctx(seeded_run),
        step_index=0,
        on_event=lambda kind, payload: events.append((kind, payload)),
    )

    skeletons = [p for k, p in events if k == "presentation_skeleton"]
    assert len(skeletons) == 1
    outline = skeletons[0]["outline"]
    assert outline and all(e["type"] for e in outline)
    # Skeleton fires before the render_ui result lands
    kinds = [k for k, _ in events]
    render_steps = [
        i
        for i, (k, p) in enumerate(events)
        if k == "step" and (p.get("step") or {}).get("tool_name") == "render_ui"
        and (p.get("step") or {}).get("type") == "tool_result"
    ]
    assert render_steps and kinds.index("presentation_skeleton") < render_steps[0]


def test_pipeline_token_usage_counts_embedded_llm_tokens(
    db_session, seeded_run, monkeypatch
):
    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)

    def fake_plan(db, ctx, *, notes="", user_id=None, workspace_id=None):
        payload = {
            "status": "planned",
            "layout_plan": {"presentation_profile": "workspace_derived"},
            "validation_status": "passed",
            "validation_errors": [],
            "model": "m",
            "prompt": "p",
            "llm_output": "{}",
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
        }
        result = {
            "plan": {"presentation_profile": "workspace_derived", "block_outline": []},
            "structured_content": ctx.structured_content,
            "validation_status": "passed",
        }
        return payload, result

    monkeypatch.setattr("app.agents.runner.visual.run_plan_layout", fake_plan)
    monkeypatch.setattr(
        "app.agents.runner.visual.run_render_ui",
        lambda *a, **k: {
            "status": "rendered",
            "spec": {"type": "generative_ui", "title": "T", "plain_summary": "s", "blocks": []},
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    )

    result = _run_visual_pipeline(
        db_session, seeded_run, ctx=_ctx(seeded_run), step_index=0
    )
    assert result.token_usage == 155


def test_lifecycle_uses_orchestrator_by_default(db_session, seeded_run, monkeypatch):
    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)
    assert settings.visual_summary_agent_loop is False

    result = _run_visual_summary_agent(
        db_session,
        seeded_run,
        step_index=0,
    )

    assert result.presentation_spec is not None
    steps = _steps(db_session, seeded_run)
    assert any(s.type == "agent_handoff" for s in steps)
    assert any(s.type == "tool_result" and s.tool_name == "render_ui" for s in steps)
    assert not any(s.type in ("thought", "final") for s in steps)


def test_render_ui_tool_skips_revalidation_for_cached_plan(monkeypatch):
    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize the workspace",
        final_answer=FINAL_ANSWER,
        structured_content={
            "summary": "React and FastAPI are the core stack; RAG shipped.",
            "key_points": ["Shipped RAG features", "TypeScript and Python"],
            "faq": [{"question": "What stack?", "answer": "React + FastAPI"}],
            "themes": ["rag", "stack"],
            "sections": [],
        },
        agent_evidence=AgentEvidenceBundle(),
    )
    tools = build_visual_tools(
        MagicMock(), workspace_id=ctx.workspace_id, user_id=ctx.user_id, ctx=ctx
    )
    by_name = {t.name: t for t in tools}
    plan_res = by_name["plan_layout"].invoke({"notes": ""})
    assert plan_res["validation_status"] == "passed"

    calls = {"n": 0}
    real_validate = visual_tools_mod.validate_layout_plan

    def counting_validate(*args, **kwargs):
        calls["n"] += 1
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(visual_tools_mod, "validate_layout_plan", counting_validate)

    # Cached plan (empty arg) → validated inside plan_layout, not again here.
    render_res = by_name["render_ui"].invoke({"layout_plan_json": "{}"})
    assert render_res["status"] == "rendered"
    assert calls["n"] == 0

    # An externally modified plan is still validated.
    import json

    modified = dict(plan_res["layout_plan"])
    modified["rationale"] = "edited by model"
    render_res2 = by_name["render_ui"].invoke(
        {"layout_plan_json": json.dumps(modified)}
    )
    assert calls["n"] == 1
    assert render_res2.get("status") == "rendered" or render_res2.get("error")
