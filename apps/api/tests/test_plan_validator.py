"""Phase B — layout plan validation."""

from app.visual_summary.planning.plan_validator import format_validator_notes, validate_layout_plan

STRUCTURED = {
    "summary": "Full-stack developer with React and FastAPI experience.",
    "key_points": ["React", "FastAPI", "RAG pipelines"],
    "faq": [{"question": "Top stack?", "answer": "React + FastAPI"}],
    "sections": [],
    "themes": [],
}


def test_validate_layout_plan_passes_complete_plan():
    plan = {
        "presentation_profile": "resume_dashboard",
        "components": ["table", "progress", "key_points"],
        "block_outline": [
            {"type": "summary", "title": "Overview", "purpose": "fit"},
            {"type": "table", "title": "Skills", "purpose": "matrix"},
            {"type": "progress", "title": "Levels", "purpose": "skills"},
        ],
        "rationale": "Resume scan layout.",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Summarize resume with table and progress bar",
        structured_content=STRUCTURED,
        requested_components=["table", "progress"],
    )
    assert ok is True
    assert errors == []


def test_validate_layout_plan_missing_requested_component():
    plan = {
        "presentation_profile": "general_summary",
        "components": ["summary"],
        "block_outline": [{"type": "summary", "title": "T", "purpose": "p"}],
        "rationale": "minimal",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Show a table of skills",
        structured_content=STRUCTURED,
        requested_components=["table"],
    )
    assert ok is False
    assert any("table" in e for e in errors)


def test_validate_layout_plan_rejects_timeline_without_dates():
    plan = {
        "presentation_profile": "timeline_view",
        "components": ["timeline"],
        "block_outline": [{"type": "timeline", "title": "Career", "purpose": "roles"}],
        "rationale": "timeline",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Show timeline of milestones",
        structured_content=STRUCTURED,
        requested_components=["timeline"],
    )
    assert ok is False
    assert any("timeline" in e.lower() for e in errors)


def test_validate_layout_plan_rejects_empty_outline_with_content():
    plan = {
        "presentation_profile": "general_summary",
        "components": [],
        "block_outline": [],
        "rationale": "empty",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Summarize",
        structured_content=STRUCTURED,
    )
    assert ok is False
    assert any("block_outline" in e for e in errors)


def test_validate_layout_plan_rejects_ungrounded_source_hint():
    plan = {
        "presentation_profile": "gap_analysis",
        "components": ["timeline"],
        "block_outline": [
            {
                "type": "timeline",
                "title": "Career",
                "source_hint": "milestones",
                "width": "full",
                "purpose": "roles",
            }
        ],
        "rationale": "bad",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Summarize",
        structured_content=STRUCTURED,
    )
    assert ok is False
    assert any("milestones" in e for e in errors)


def test_validate_layout_plan_accepts_grounded_source_hints():
    plan = {
        "presentation_profile": "workspace_derived",
        "components": ["summary", "key_points"],
        "block_outline": [
            {
                "type": "summary",
                "title": "Overview",
                "source_hint": "summary",
                "width": "full",
            },
            {
                "type": "key_points",
                "title": "Highlights",
                "source_hint": "key_points",
                "width": "half",
            },
        ],
        "rationale": "ok",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Summarize",
        structured_content=STRUCTURED,
    )
    assert ok is True, errors
    assert errors == []


def test_validate_layout_plan_drops_invalid_width_non_fatal():
    plan = {
        "presentation_profile": "workspace_derived",
        "components": ["summary"],
        "block_outline": [
            {
                "type": "summary",
                "title": "Overview",
                "source_hint": "summary",
                "width": "triple",
            }
        ],
        "rationale": "ok",
    }
    ok, errors = validate_layout_plan(
        plan,
        goal="Summarize",
        structured_content=STRUCTURED,
    )
    assert ok is True, errors
    assert "width" not in plan["block_outline"][0]


def test_format_validator_notes_lists_errors():
    notes = format_validator_notes(["Missing table", "Empty outline"])
    assert "VALIDATION FAILED" in notes
    assert "Missing table" in notes