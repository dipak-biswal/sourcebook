"""#3 — structured content is resolved once and reused."""

import uuid
from unittest.mock import patch

from app.agents.visual_tools import _ensure_structured, _plan_layout_skeleton
from app.presentation.context import PresentationContext


def _ctx(**kwargs) -> PresentationContext:
    base = dict(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Explain the topic",
        final_answer=(
            "A distributed system is multiple nodes cooperating.\n\n"
            "- Partial failure is normal\n"
            "- Pick consistency per use case\n"
        ),
    )
    base.update(kwargs)
    return PresentationContext(**base)


def test_ensure_structured_uses_ctx_without_reextract():
    existing = {
        "summary": "Pinned summary from handoff.",
        "key_points": ["A", "B"],
        "faq": [],
        "sections": [],
    }
    ctx = _ctx(structured_content=existing, structured_source="llm")
    with patch(
        "app.agents.visual_tools.extract_structured_content",
        side_effect=AssertionError("must not re-extract"),
    ):
        out = _ensure_structured(ctx)
    assert out["summary"] == "Pinned summary from handoff."
    assert ctx.structured_content is not None
    assert ctx.structured_content["summary"] == "Pinned summary from handoff."


def test_ensure_structured_extracts_once_when_missing():
    ctx = _ctx(structured_content=None)
    with patch(
        "app.agents.visual_tools.extract_structured_content",
        return_value={
            "summary": "From heuristic.",
            "key_points": ["One", "Two"],
            "faq": [],
            "sections": [],
        },
    ) as mock_extract:
        first = _ensure_structured(ctx)
        second = _ensure_structured(ctx)
    assert mock_extract.call_count == 1
    assert first["summary"] == "From heuristic."
    assert second["summary"] == "From heuristic."
    assert ctx.structured_source == "heuristic"


def test_skeleton_does_not_reextract_when_ctx_set():
    ctx = _ctx(
        structured_content={
            "summary": "Overview already resolved for the plan.",
            "key_points": ["Point one", "Point two", "Point three"],
            "faq": [{"question": "Why?", "answer": "Because."}],
            "themes": ["alpha", "beta"],
            "sections": [],
        },
        structured_source="llm",
    )
    with patch(
        "app.agents.visual_tools.extract_structured_content",
        side_effect=AssertionError("skeleton must not re-extract"),
    ):
        result = _plan_layout_skeleton(ctx)
    assert result["structured_content"]["summary"].startswith("Overview already")
    assert result["plan"]["block_outline"]
