"""Structured content extraction for visual summary planning."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.visual_tools import _plan_layout_llm
from app.presentation.context import PresentationContext
from app.presentation.evidence import AgentEvidenceBundle, DocumentEvidenceHit
from app.presentation.structured import (
    build_plan_layout_input,
    extract_structured_content,
    format_plan_layout_prompt,
)


SAMPLE_ANSWER = """\
This workspace covers full-stack AI developer positioning.

## Key Points
- Shipped RAG pipelines with eval harnesses
- TypeScript/React and Python/FastAPI production experience
- Postgres + vector search in deployed products

## FAQ
**Q: What stack should I emphasize?**
A: Lead with shipped LLM features, then TypeScript/React and FastAPI.

**Q: What is weak?**
A: Generic AI enthusiasm without measurable outcomes.
"""


def test_extract_structured_content_parses_sections():
    structured = extract_structured_content(SAMPLE_ANSWER, goal="Explain with FAQ")
    assert "full-stack AI" in structured["summary"]
    assert any("RAG" in p for p in structured["key_points"])
    assert len(structured["faq"]) >= 2
    assert structured["faq"][0]["question"].endswith("?")


def test_plan_layout_prompt_uses_structured_input_not_raw_answer(monkeypatch):
    long_tail = "extra detail " * 500
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Explain documents with key points and FAQ",
        final_answer=SAMPLE_ANSWER + long_tail,
        structured_content=extract_structured_content(SAMPLE_ANSWER, goal="Explain"),
        agent_evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(filename="resume.pdf", snippet="Built RAG agent.")
            ]
        ),
    )

    captured: list[str] = []

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"presentation_profile":"concept_guide","components":["faq","key_points"],"block_outline":[],"rationale":"ok"}'
                )
            )
        ]
        usage = SimpleNamespace(prompt_tokens=80, completion_tokens=20)

    def fake_create(**kwargs):
        captured.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.agents.visual_tools._client", lambda: fake_client)

    result = _plan_layout_llm(ctx)
    prompt = captured[0]
    assert "STRUCTURED INPUT" in prompt
    assert '"structured_content"' in prompt or "structured_content" in prompt
    assert long_tail not in prompt
    assert result["structured_input"]["structured_content"]["key_points"]
    assert "resume.pdf" in format_plan_layout_prompt(
        build_plan_layout_input(
            goal=ctx.goal,
            structured_content=ctx.structured_content or {},
            evidence=ctx.agent_evidence,
            components=["faq"],
        ),
        layout_hints="hints",
    )