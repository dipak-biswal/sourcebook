"""Presentation planner human-in-the-loop gates."""

from app.presentation.planner import should_offer_presentation, should_render_presentation


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


def test_should_render_is_narrower_than_offer():
    goal = "Tell me about my uploaded files"
    answer = "A" * 50
    assert should_offer_presentation(goal=goal, final_answer=answer, status="completed")
    assert not should_render_presentation(goal=goal, final_answer=answer, status="completed")