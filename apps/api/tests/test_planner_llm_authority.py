"""LLM-primary layout planner authority (grounded plans + skeleton fallback)."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.visual_tools import _plan_with_validation
from app.presentation.context import PresentationContext
from app.presentation.evidence import AgentEvidenceBundle
from app.presentation.render_blocks import assemble_blocks
from app.presentation.ui_intent import available_source_hints

STRUCTURED = {
    "summary": "Developer with React and Python experience across two products.",
    "key_points": ["React", "FastAPI", "Shipped RAG pipelines"],
    "faq": [{"question": "Top stack?", "answer": "React + FastAPI"}],
    "sections": [],
    "themes": ["frontend", "backend"],
    "matrix_rows": [
        "Requirement | Evidence | Status",
        "React | Lead role | Strong",
        "AWS | Mentioned once | Gap",
    ],
    "levels": ["React | Strong", "AWS | Gap"],
    "gaps": ["AWS depth is the main gap for cloud-heavy roles."],
}


def _ctx(**overrides) -> PresentationContext:
    base = dict(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Compare React vs AWS readiness with a table",
        final_answer="Answer with enough detail for presentation.",
        structured_content=STRUCTURED,
        agent_evidence=AgentEvidenceBundle(),
    )
    base.update(overrides)
    return PresentationContext(**base)


def _fake_llm(plan: dict, monkeypatch, calls: list | None = None):
    class _FakeResp:
        def __init__(self, content: str):
            self.choices = [
                SimpleNamespace(message=SimpleNamespace(content=content))
            ]
            self.usage = SimpleNamespace(prompt_tokens=40, completion_tokens=20)

    def fake_create(**kwargs):
        if calls is not None:
            calls.append(kwargs["messages"][1]["content"])
        return _FakeResp(json.dumps(plan))

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)


def test_available_source_hints_lists_present_fields_only():
    present = available_source_hints(STRUCTURED)
    assert "summary" in present
    assert "key_points" in present
    assert "matrix_rows" in present
    assert "levels" in present
    assert "faq" in present
    assert "themes" in present
    assert "milestones" not in present
    assert "metrics" not in present


def test_planner_valid_grounded_plan_used_verbatim(monkeypatch):
    """Planner output with valid grounded plan → used as-is (order + width)."""
    llm_plan = {
        "presentation_profile": "gap_analysis",
        "components": ["table", "key_points", "callout"],
        "block_outline": [
            {
                "type": "table",
                "title": "Résumé vs bar",
                "source_hint": "matrix_rows",
                "width": "full",
                "purpose": "Gap comparison",
            },
            {
                "type": "key_points",
                "title": "Highlights",
                "source_hint": "key_points",
                "width": "half",
                "purpose": "Bullets",
            },
            {
                "type": "callout",
                "title": "Priority",
                "source_hint": "priority_message",
                "width": "half",
                "purpose": "Main gap",
            },
        ],
        "rationale": "Lead with comparison for the goal.",
    }
    _fake_llm(llm_plan, monkeypatch)
    monkeypatch.setattr(
        "app.agents.visual_tools.settings.visual_summary_llm_planner", True
    )

    result = _plan_with_validation(_ctx())
    assert result["validation_status"] == "passed"
    assert result["replan_attempted"] is False
    outline = result["plan"]["block_outline"]
    assert outline[0]["type"] == "table"
    assert outline[0]["title"] == "Résumé vs bar"
    assert outline[0]["width"] == "full"
    assert outline[1]["width"] == "half"
    assert result["usage"]["prompt_tokens"] == 40


def test_planner_absent_source_hint_falls_back_to_skeleton(monkeypatch):
    """Ungrounded source_hint fails validation → skeleton fallback."""
    bad_plan = {
        "presentation_profile": "gap_analysis",
        "components": ["timeline"],
        "block_outline": [
            {
                "type": "timeline",
                "title": "Career",
                "source_hint": "milestones",  # not present in STRUCTURED
                "width": "full",
                "purpose": "fake",
            }
        ],
        "rationale": "bad",
    }
    # First call (primary) and optional repair both return ungrounded plan
    calls: list[str] = []

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(bad_plan))
            )
        ]
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def fake_create(**kwargs):
        calls.append("call")
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)
    monkeypatch.setattr(
        "app.agents.visual_tools.settings.visual_summary_llm_planner", True
    )

    result = _plan_with_validation(_ctx())
    assert len(calls) >= 1  # primary (+ repair)
    # Skeleton fallback
    assert result["plan"]["presentation_profile"] == "workspace_derived"
    assert result["plan"]["block_outline"]
    assert all(
        b.get("source_hint") != "milestones" or b.get("source_hint") in available_source_hints(STRUCTURED)
        for b in result["plan"]["block_outline"]
    )
    # No milestones in skeleton for this structured content
    assert not any(
        b.get("source_hint") == "milestones" for b in result["plan"]["block_outline"]
    )


def test_planner_invalid_json_falls_back_to_skeleton(monkeypatch):
    class _FakeResp:
        choices = [
            SimpleNamespace(message=SimpleNamespace(content="not-json{{{"))
        ]
        usage = SimpleNamespace(prompt_tokens=8, completion_tokens=2)

    fake_client = MagicMock()
    fake_client.chat.completions.create = lambda **kwargs: _FakeResp()
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)
    monkeypatch.setattr(
        "app.agents.visual_tools.settings.visual_summary_llm_planner", True
    )

    result = _plan_with_validation(_ctx())
    # _plan_layout_llm already swaps invalid JSON for skeleton plan
    assert result["validation_status"] == "passed"
    assert result["plan"]["block_outline"]


def test_assembly_honors_explicit_width_from_plan():
    """Width from the plan is honored even when default would differ."""
    outline = [
        {
            "type": "table",
            "title": "Compare",
            "source_hint": "matrix_rows",
            "width": "half",  # tables default full; explicit half must stick
        }
    ]
    blocks, dropped = assemble_blocks(outline, STRUCTURED)
    assert not dropped
    assert len(blocks) == 1
    assert blocks[0].type == "table"
    assert blocks[0].width == "half"


def test_prompt_includes_available_fields_whitelist(monkeypatch):
    calls: list[str] = []
    good_plan = {
        "presentation_profile": "workspace_derived",
        "components": ["summary"],
        "block_outline": [
            {
                "type": "summary",
                "title": "Overview",
                "source_hint": "summary",
                "width": "full",
                "purpose": "overview",
            }
        ],
        "rationale": "ok",
    }
    _fake_llm(good_plan, monkeypatch, calls=calls)
    monkeypatch.setattr(
        "app.agents.visual_tools.settings.visual_summary_llm_planner", True
    )

    _plan_with_validation(_ctx())
    assert calls
    prompt = calls[0]
    assert "AVAILABLE SOURCE FIELDS" in prompt
    assert "matrix_rows" in prompt
    assert "source_hint" in prompt
    assert '"width"' in prompt or "width" in prompt
