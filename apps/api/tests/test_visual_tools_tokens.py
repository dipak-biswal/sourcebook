"""Visual Summary tool token capture."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.visual_summary.tools import _plan_layout_llm
from app.visual_summary.context import PresentationContext
from app.visual_summary.handoff.evidence import AgentEvidenceBundle


def test_plan_layout_llm_returns_prompt_and_usage(monkeypatch):
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize resume",
        final_answer="Detailed answer text.",
        agent_evidence=AgentEvidenceBundle(),
    )

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"presentation_profile":"resume_dashboard","components":[],"block_outline":[],"rationale":"ok"}'
                )
            )
        ]
        usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30)

    fake_client = MagicMock()
    fake_client.chat.completions.create = lambda **kwargs: _FakeResp()
    monkeypatch.setattr("app.visual_summary.tools._client", lambda: fake_client)

    result = _plan_layout_llm(ctx)
    assert "STRUCTURED INPUT" in result["prompt"]
    assert "structured_content" in result["prompt"]
    assert result["llm_output"]
    assert result["usage"]["prompt_tokens"] == 120
    assert result["usage"]["completion_tokens"] == 30
    assert result["usage"]["total_tokens"] == 150