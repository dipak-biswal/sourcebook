"""Workspace Context Agent — readiness, questions, merge, phase helpers."""

from __future__ import annotations

from app.agents.context.curator import curate_main_agent_prompt
from app.agents.context.merge import (
    CollectedContextSnapshot,
    answers_to_snapshot,
    format_collected_context,
)
from app.agents.context.phase import is_questions_pending
from app.agents.context.questions import always_plan_questions, template_questions_for_gaps
from app.agents.context.readiness import Gap, assess_readiness
from app.agents.context.workspace_apply import apply_snapshot_to_workspace
from app.agents.visual_summary.workspace.context import derive_workspace_context
from app.config import settings
from app.models import Workspace


def _thin_packet():
    return derive_workspace_context(
        name="Untitled",
        description=None,
        tags=None,
        document_rows=[],
    )


def _rich_packet():
    return derive_workspace_context(
        name="Learn System Design",
        description=(
            "This workspace is for studying distributed systems from my notes. "
            "Help me understand concepts and design simple systems. "
            "Audience: me. Success: I can explain tradeoffs."
        ),
        tags=["learning", "systems"],
        document_rows=[("notes.pdf", "ready"), ("cap-theorem.md", "ready")],
    )


def test_assess_readiness_thin_and_vague_has_gaps():
    packet = _thin_packet()
    gaps = assess_readiness(packet, "learn")
    ids = {g.id for g in gaps}
    assert "thin_workspace" in ids
    assert "vague_goal" in ids


def test_assess_readiness_rich_and_clear_skips():
    packet = _rich_packet()
    gaps = assess_readiness(
        packet,
        "Explain the CAP theorem tradeoffs using my notes on distributed systems",
    )
    # Rich description + clear multi-token goal + ready docs → no collector
    assert gaps == []


def test_always_plan_questions_returns_form():
    qs = always_plan_questions(_thin_packet(), "Explain event loops", max_questions=4)
    assert 1 <= len(qs) <= 4
    assert qs[0]["id"] == "topic_scope"


def test_assess_readiness_docs_implied_without_files():
    packet = _thin_packet()
    gaps = assess_readiness(packet, "Summarize my resume for a senior role")
    ids = {g.id for g in gaps}
    assert "docs_implied" in ids


def test_assess_readiness_url_missing():
    packet = _rich_packet()
    gaps = assess_readiness(packet, "Summarize this article for me please")
    ids = {g.id for g in gaps}
    assert "url_missing" in ids


def test_template_questions_stable_ids_and_cap():
    gaps = [
        Gap(id="vague_goal", reason="x", severity="high"),
        Gap(id="research_unscoped", reason="y", severity="medium"),
        Gap(id="audience_unknown", reason="z", severity="low"),
        Gap(id="url_missing", reason="u", severity="high"),
    ]
    qs = template_questions_for_gaps(gaps, _thin_packet(), "learn HTTP", max_questions=4)
    assert 1 <= len(qs) <= 4
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids))
    assert any(q["input"] in ("text", "checkbox") for q in qs)
    # At least one checkbox for level-like closed choice when research/vague
    assert any(q["input"] == "checkbox" for q in qs)


def test_apply_snapshot_fills_empty_workspace_only(db_session=None):
    # Lightweight unit test without full DB fixture: mock Workspace-like object.
    class W:
        description = None
        tags = None
        context_cache = {"x": 1}

    class FakeDB:
        def __init__(self):
            self.committed = False

        def add(self, _w):
            pass

        def commit(self):
            self.committed = True

        def refresh(self, _w):
            pass

    w = W()
    db = FakeDB()
    snap = CollectedContextSnapshot(
        topic_focus="Event loop",
        audience="Myself",
        level="Beginner",
        workspace_framing="Learn JS concurrency",
    )
    changed = apply_snapshot_to_workspace(db, w, snap)  # type: ignore[arg-type]
    assert changed["updated"] is True
    assert "Event loop" in (w.description or "") or "Learn JS" in (w.description or "")
    assert w.context_cache is None
    assert db.committed is True

    # Non-empty description is preserved
    w2 = W()
    w2.description = "Already set"
    w2.tags = ["existing"]
    changed2 = apply_snapshot_to_workspace(db, w2, snap)  # type: ignore[arg-type]
    assert w2.description == "Already set"
    assert "Beginner" in (w2.tags or [])


def test_curator_heuristic_brief(monkeypatch):
    monkeypatch.setattr(settings, "context_curator_enabled", False)
    packet = _rich_packet()
    snap = CollectedContextSnapshot(topic_focus="CAP theorem", level="Beginner")
    out = curate_main_agent_prompt(packet, "Explain CAP", snap)
    assert out["system_addendum"]
    assert "CAP" in out["curated_goal"] or "Explain" in out["curated_goal"]
    assert out["source"] == "heuristic"


def test_merge_answers_to_prompt_block():
    snap = answers_to_snapshot(
        {
            "topic_scope": "HTTP request lifecycle",
            "level": "beginner",
            "urls": "https://example.com/http\nhttps://mdn.io",
            "document_plan": "web",
        },
        questions=[
            {
                "id": "level",
                "input": "checkbox",
                "options": [
                    {"id": "beginner", "label": "Beginner"},
                    {"id": "advanced", "label": "Advanced"},
                ],
            },
            {
                "id": "document_plan",
                "input": "checkbox",
                "options": [
                    {"id": "web", "label": "Use the web"},
                    {"id": "upload", "label": "I'll upload documents"},
                ],
            },
        ],
    )
    assert snap.topic_focus == "HTTP request lifecycle"
    assert snap.level == "Beginner"
    assert snap.document_plan == "Use the web"
    assert "https://example.com/http" in snap.urls
    block = format_collected_context(snap)
    assert "COLLECTED RUN CONTEXT" in block
    assert "HTTP request lifecycle" in block
    assert "Beginner" in block
    # Empty snapshot → empty block
    assert format_collected_context(answers_to_snapshot({})) == ""


def test_is_questions_pending():
    assert is_questions_pending({"kind": "questions", "name": "ask_user"})
    assert is_questions_pending({"name": "ask_user"})
    assert not is_questions_pending({"kind": "presentation", "name": "generative_ui"})
    assert not is_questions_pending(None)
