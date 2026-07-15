"""Plan layout prefers code skeleton; LLM only for repair notes."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.visual_tools import _plan_with_validation
from app.presentation.context import PresentationContext
from app.presentation.evidence import AgentEvidenceBundle

STRUCTURED = {
    "summary": "Developer with React and Python experience.",
    "key_points": ["React", "FastAPI"],
    "faq": [],
    "sections": [],
    "themes": [],
}


def test_plan_with_validation_uses_code_skeleton_by_default():
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize materials with table",
        final_answer="Answer with enough detail for presentation.",
        structured_content=STRUCTURED,
        agent_evidence=AgentEvidenceBundle(),
    )
    result = _plan_with_validation(ctx)
    assert result["validation_status"] == "passed"
    assert result["replan_attempted"] is False
    assert result["usage"]["model"] == "code_skeleton"
    assert result["plan"]["presentation_profile"] == "workspace_derived"
    assert any(b.get("type") == "summary" for b in result["plan"]["block_outline"])


def test_plan_with_validation_can_call_llm_when_notes_provided(monkeypatch):
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize with key points",
        final_answer="Answer with enough detail.",
        structured_content=STRUCTURED,
        agent_evidence=AgentEvidenceBundle(),
    )

    refined = {
        "presentation_profile": "workspace_derived",
        "components": ["summary", "key_points"],
        "block_outline": [
            {
                "type": "summary",
                "title": "Role fit",
                "purpose": "overview",
                "source_hint": "summary",
            },
            {
                "type": "key_points",
                "title": "Highlights",
                "purpose": "bullets",
                "source_hint": "key_points",
            },
        ],
        "rationale": "refined titles",
    }

    class _FakeResp:
        def __init__(self):
            import json

            self.choices = [
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(refined)))
            ]
            self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    calls: list[str] = []

    def fake_create(**kwargs):
        calls.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)

    result = _plan_with_validation(ctx, notes="Prefer clearer titles")
    assert result["replan_attempted"] is True
    assert len(calls) == 1
    assert result["validation_status"] == "passed"
