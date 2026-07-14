"""Layout intent parsing from user goals."""

from app.presentation.layout import format_layout_requirements, layout_components_from_goal


def test_parses_kitchen_sink_goal():
    goal = (
        "Build a visual summary: skill table, progress bars, filter chips "
        "for Technical vs Leadership, callout for main gap"
    )
    components = layout_components_from_goal(goal)
    assert "table" in components
    assert "progress" in components
    assert "chips" in components
    assert "callout" in components


def test_format_layout_lists_required_types():
    text = format_layout_requirements(["table", "progress", "callout"])
    assert "table" in text
    assert "progress" in text
    assert "callout" in text
    assert "MUST include" in text