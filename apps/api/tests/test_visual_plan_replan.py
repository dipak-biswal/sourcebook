"""Phase B — plan_layout auto-replan on validator failure."""

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

BAD_PLAN = (
    '{"presentation_profile":"x","components":["summary"],'
    '"block_outline":[{"type":"summary","title":"T","purpose":"p"}],'
    '"rationale":"missing table"}'
)
GOOD_PLAN = (
    '{"presentation_profile":"resume_dashboard","components":["table","key_points"],'
    '"block_outline":[{"type":"table","title":"Skills","purpose":"matrix"},'
    '{"type":"key_points","title":"Highlights","purpose":"bullets"}],'
    '"rationale":"ok"}'
)


def test_plan_with_validation_auto_replans(monkeypatch):
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize resume with table",
        final_answer="Answer with enough detail.",
        structured_content=STRUCTURED,
        agent_evidence=AgentEvidenceBundle(),
    )

    responses = [BAD_PLAN, GOOD_PLAN]
    calls: list[str] = []

    class _FakeResp:
        def __init__(self, content: str):
            self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]
            self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def fake_create(**kwargs):
        content = responses.pop(0)
        calls.append(kwargs["messages"][1]["content"])
        return _FakeResp(content)

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)

    result = _plan_with_validation(ctx)
    assert result["validation_status"] == "passed"
    assert result["replan_attempted"] is True
    assert len(calls) == 2
    assert "VALIDATION FAILED" in calls[1]