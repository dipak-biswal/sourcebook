"""Presentation planner human-in-the-loop gates."""

from app.visual_summary.planning.planner import should_offer_presentation


def test_should_offer_presentation_for_substantive_answer():
    assert should_offer_presentation(
        goal="Summarize my resume for a full-stack role",
        final_answer="You have strong experience across React, FastAPI, and LLM tooling.",
        status="completed",
    )


def test_should_not_offer_for_operational_goals():
    assert not should_offer_presentation(
        goal="Create a note titled Demo with body hello",
        final_answer="Here is a draft note body with enough characters to pass the length gate.",
        status="completed",
    )


def test_should_not_offer_for_short_answers():
    assert not should_offer_presentation(
        goal="Explain quantum computing",
        final_answer="Too short",
        status="completed",
    )