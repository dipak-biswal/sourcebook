"""Presentation engine anti-hallucination helpers."""

from app.visual_summary.blocks.gen_ui import GenUIBlock
from app.visual_summary.render.engine import (
    _looks_like_placeholder,
    _phrase_grounded,
    _sanitize_blocks_for_grounding,
    _timeline_item_grounded,
)


def test_rejects_placeholder_timeline_companies():
    item = "2023 - Present: Senior Full-Stack Developer at XYZ Corp"
    corpus = "dipak built rag systems at acme real employer with react and fastapi"
    assert not _timeline_item_grounded(item, corpus)


def test_accepts_grounded_timeline_entry():
    item = "2020 - 2024: Engineer at Acme Real Employer"
    corpus = "worked at acme real employer building react apps"
    assert _timeline_item_grounded(item, corpus)


def test_sanitize_drops_hallucinated_timeline_block():
    blocks = [
        GenUIBlock(
            type="timeline",
            title="Roles",
            items=[
                "2023 - Present: Senior Dev at XYZ Corp",
                "2021 - 2023: Dev at ABC Inc",
            ],
        ),
        GenUIBlock(type="summary", title="Overview", body="Real summary from resume."),
    ]
    out = _sanitize_blocks_for_grounding(
        blocks,
        answer="Real summary from resume. Skills: React, Python.",
        context="[1] resume.pdf\nBuilt APIs at Contoso with FastAPI",
    )
    types = [b.type for b in out]
    assert "timeline" not in types
    assert "summary" in types


def test_phrase_grounded_requires_contiguous_span():
    """Tokens recombined from distant sentences must not pass as a grounded phrase."""
    corpus = (
        "acme systems shipped the platform. "
        "later the real employer hired contractors. "
        "unrelated mention of acme again."
    )
    # "Acme Real Employer" never appears as a contiguous span.
    assert not _phrase_grounded("Acme Real Employer", corpus)
    # Contiguous span still passes.
    assert _phrase_grounded(
        "Acme Real Employer",
        "worked at acme real employer building react apps",
    )


def test_placeholder_detects_emails_urls_and_lorem():
    assert _looks_like_placeholder("Contact jane@example.com for details")
    assert _looks_like_placeholder("See https://www.example.com/docs")
    assert _looks_like_placeholder("Lorem ipsum dolor sit amet")
    assert _looks_like_placeholder("Started 01/01/2020 at Foo Bar")
    assert not _looks_like_placeholder("Built APIs at Contoso with FastAPI")