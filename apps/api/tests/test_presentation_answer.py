"""Presentation handoff answer resolution and clipping."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.visual_summary.tools import _plan_layout_llm
from app.visual_summary.render.answer import (
    PRESENTATION_ANSWER_MAX_CHARS,
    clip_presentation_answer,
    resolve_presentation_answer,
)
from app.visual_summary.context import PresentationContext
from app.visual_summary.handoff.evidence import AgentEvidenceBundle
from app.visual_summary.handoff.structured import extract_structured_content


def test_resolve_presentation_answer_prefers_longest_narrative():
    short = "Brief closing note."
    long = "A" * 500
    steps = [
        SimpleNamespace(step_index=1, type="final", output=short),
        SimpleNamespace(step_index=2, type="synthesis", output=long),
    ]
    resolved = resolve_presentation_answer(final_answer=short, steps=steps)
    assert resolved == long


def test_resolve_presentation_answer_ignores_waiting_approval_placeholder():
    steps = [
        SimpleNamespace(
            step_index=1,
            type="final",
            output="Full substantive answer with enough detail for layout planning.",
        )
    ]
    resolved = resolve_presentation_answer(
        final_answer="Waiting for your approval to run `generative_ui`.",
        steps=steps,
    )
    assert "substantive answer" in resolved


def test_clip_presentation_answer_keeps_short_text():
    text = "Short answer."
    clipped, truncated = clip_presentation_answer(text)
    assert clipped == text
    assert truncated is False


def test_clip_presentation_answer_truncates_very_long_text():
    text = "Paragraph one.\n\n" + ("detail " * 8000)
    clipped, truncated = clip_presentation_answer(
        text,
        max_chars=200,
    )
    assert truncated is True
    assert len(clipped) <= 260
    assert "truncated" in clipped.lower()


def test_plan_layout_prompt_uses_structured_extract_not_raw_blob(monkeypatch):
    long_answer = "## Key Points\n- Alpha\n\n" + ("Z" * 9000)
    structured = extract_structured_content(long_answer, goal="Summarize resume")
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize resume with visual summary",
        final_answer=long_answer,
        structured_content=structured,
        agent_evidence=AgentEvidenceBundle(),
    )

    captured: list[str] = []

    class _FakeResp:
        choices = [SimpleNamespace(message=SimpleNamespace(content='{"presentation_profile":"x","components":[],"block_outline":[],"rationale":""}'))]
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def fake_create(**kwargs):
        captured.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.visual_summary.tools._client", lambda: fake_client)

    _plan_layout_llm(ctx)
    prompt = captured[0]
    assert "STRUCTURED INPUT" in prompt
    assert "ZZZZZZ" not in prompt
    assert len(long_answer) > 6000