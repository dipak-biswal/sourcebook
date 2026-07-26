"""Progressive Visual Summary assembly (text-first + figure upgrade)."""

from app.agents.visual_summary.streaming.progressive import (
    FIGURE_BLOCK_TYPES,
    empty_partial_spec,
    progressive_assemble_presentation,
    should_use_progressive_render,
)
from tests.test_study_sheet import _outbox_answer
from app.agents.visual_summary.handoff.structured import extract_structured_content
from app.agents.visual_summary.planning.study_sheet import build_topic_study_sheet_plan


def test_should_use_progressive_for_multi_block_outline():
    assert not should_use_progressive_render(None)
    assert not should_use_progressive_render({"block_outline": []})
    assert not should_use_progressive_render(
        {"block_outline": [{"type": "summary", "title": "Only one"}]}
    )
    assert should_use_progressive_render(
        {
            "block_outline": [
                {"type": "summary", "title": "A"},
                {"type": "key_points", "title": "B"},
            ]
        }
    )


def test_progressive_study_sheet_emits_panels_in_order():
    goal = "Create a complete study sheet for the Outbox Pattern"
    answer = _outbox_answer()
    structured = extract_structured_content(answer, goal=goal)
    plan = build_topic_study_sheet_plan(structured, goal=goal)
    assert plan is not None
    assert should_use_progressive_render(plan)

    events: list[dict] = []

    def on_panel(payload: dict) -> None:
        events.append(payload)

    spec = progressive_assemble_presentation(
        plan,
        structured,
        goal=goal,
        workspace_name="System Design",
        on_panel=on_panel,
    )

    assert spec.get("type") == "generative_ui"
    assert spec.get("status") == "complete"
    blocks = spec.get("blocks") or []
    assert len(blocks) >= 4

    # At least one text paint per panel that assembled
    text_events = [e for e in events if e.get("phase") == "text"]
    assert len(text_events) >= 4
    # ready_count grows
    counts = [e["ready_count"] for e in text_events]
    assert counts == sorted(counts)
    assert counts[-1] >= 4

    complete = [e for e in events if e.get("phase") == "complete"]
    assert len(complete) == 1

    # Partial snapshots always include all ready blocks so far
    for e in text_events:
        snap = e["presentation_spec"]
        assert len(snap.get("blocks") or []) == e["ready_count"]


def test_figure_types_get_text_first_then_upgrade_when_graph_exists():
    structured = {
        "summary": "How outbox works",
        "sections": [
            {
                "heading": "2. High Level Flow",
                "body": "Business op → Write DB → Outbox → Publish → Consume",
                "bullets": [
                    "Business operation",
                    "Write to database",
                    "Write outbox",
                    "Publish to broker",
                ],
            },
            {
                "heading": "9. Best Practices",
                "body": "",
                "bullets": ["Index status", "Idempotent consumers", "Monitor failures"],
            },
        ],
        "key_points": [],
        "faq": [],
        "themes": [],
    }
    plan = {
        "presentation_profile": "topic_study_sheet",
        "block_outline": [
            {
                "type": "flow_diagram",
                "title": "2. High Level Flow",
                "source_hint": "process_flow",
                "width": "full",
                "section_index": 1,
                "panel_index": 1,
            },
            {
                "type": "key_points",
                "title": "9. Best Practices",
                "source_hint": "key_points",
                "width": "full",
                "section_index": 2,
                "panel_index": 2,
            },
        ],
    }

    phases: list[tuple[str, int, str | None]] = []

    def on_panel(payload: dict) -> None:
        b = payload.get("block") or {}
        phases.append(
            (
                str(payload.get("phase")),
                int(payload.get("panel_index") or 0),
                str(b.get("type")) if b else None,
            )
        )

    spec = progressive_assemble_presentation(
        plan,
        structured,
        goal="Teach me outbox high level flow",
        on_panel=on_panel,
    )

    assert any(p[0] == "text" and p[1] == 1 for p in phases)
    # Text-first for figure panels uses key_points/steps, not flow_diagram
    text_panel1 = next(p for p in phases if p[0] == "text" and p[1] == 1)
    assert text_panel1[2] in ("key_points", "steps", "summary")

    # Figure upgrade when process_flow graph is present
    figure_events = [p for p in phases if p[0] == "figure" and p[1] == 1]
    assert figure_events, "expected figure upgrade for pipeline section"
    assert figure_events[0][2] == "flow_diagram"

    final_types = [b.get("type") for b in (spec.get("blocks") or [])]
    assert "flow_diagram" in final_types
    assert "key_points" in final_types

    # Composite: upgraded flow panel keeps teaching bullets
    flow = next(
        b for b in (spec.get("blocks") or []) if b.get("type") == "flow_diagram"
    )
    assert flow.get("items") or flow.get("body"), "figure should keep prose companion"


def test_empty_partial_spec_shape():
    plan = {
        "presentation_profile": "topic_study_sheet",
        "block_outline": [{"type": "summary", "title": "1. Why"}],
    }
    shell = empty_partial_spec(
        plan,
        goal="study sheet",
        workspace_name="Learn SD",
        structured={"summary": "hello"},
        expected_count=3,
    )
    assert shell["type"] == "generative_ui"
    assert shell["status"] == "streaming"
    assert shell["blocks"] == []
    assert shell["expected_count"] == 3
    assert shell["ready_count"] == 0
    assert shell["assembly_meta"]["progressive"] is True


def test_figure_block_types_constant():
    assert "flow_diagram" in FIGURE_BLOCK_TYPES
    assert "sequence_diagram" in FIGURE_BLOCK_TYPES
