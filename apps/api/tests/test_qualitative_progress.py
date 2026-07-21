"""Qualitative progress bar normalization."""

from app.visual_summary.blocks.gen_ui import GenUIBlock
from app.visual_summary.render.engine import _normalize_qualitative_progress


def test_strips_ungrounded_percentage():
    blocks = [
        GenUIBlock(
            type="progress",
            title="Skills",
            items=["Frontend Development | 90"],
        )
    ]
    answer = (
        "Frontend Development: Strong expertise in React and TypeScript. "
        "AI Depth: foundational understanding."
    )
    out = _normalize_qualitative_progress(blocks, answer=answer)
    assert out[0].items
    assert "90" not in out[0].items[0]
    assert "Strong" in out[0].items[0] or "Moderate" in out[0].items[0]


def test_keeps_explicit_percentage_from_answer():
    blocks = [
        GenUIBlock(type="progress", items=["Test Coverage | 85%"]),
    ]
    answer = "Achieved 85% test coverage on the core platform."
    out = _normalize_qualitative_progress(blocks, answer=answer)
    assert "85" in out[0].items[0]