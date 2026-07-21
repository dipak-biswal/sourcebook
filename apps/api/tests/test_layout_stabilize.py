"""Stabilize layout plans: profiles, diagram injection, mechanism order."""

from app.presentation.layout_stabilize import (
    sanitize_presentation_profile,
    stabilize_layout_plan,
    stabilize_process_flow_topology,
)
from app.presentation.render_blocks import payload_from_assembly


def test_sanitize_rejects_short_snake_case_placeholder():
    assert (
        sanitize_presentation_profile("short_snake_case", goal="explain event loop")
        == "mechanism_explainer"
    )
    assert (
        sanitize_presentation_profile("short snake case", goal="explain eventloop")
        == "mechanism_explainer"
    )
    assert (
        sanitize_presentation_profile("event_loop_explanation", goal="explain x")
        == "event_loop_explanation"
    )


def test_stabilize_injects_diagrams_when_data_present():
    structured = {
        "summary": "The event loop coordinates async work.",
        "key_points": ["Single threaded"],
        "process_flow": {
            "nodes": [
                {"id": "call_stack", "label": "Call Stack"},
                {"id": "web_apis", "label": "Web APIs"},
                {"id": "queue", "label": "Callback Queue"},
            ],
            "edges": [
                {"source": "call_stack", "target": "web_apis", "label": "timer"},
                {"source": "web_apis", "target": "queue", "label": "ready"},
            ],
        },
        "interaction_sequence": {
            "actors": ["Call Stack", "Web APIs", "Callback Queue"],
            "messages": [
                {
                    "source": "Call Stack",
                    "target": "Web APIs",
                    "label": "setTimeout",
                    "order": 0,
                },
                {
                    "source": "Web APIs",
                    "target": "Callback Queue",
                    "label": "enqueue",
                    "order": 1,
                },
            ],
        },
    }
    plan = {
        "presentation_profile": "short_snake_case",
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
                "title": "Points",
                "source_hint": "key_points",
                "width": "half",
            },
        ],
    }
    out = stabilize_layout_plan(
        plan,
        structured=structured,
        skeleton_plan={
            "presentation_profile": "workspace_derived",
            "block_outline": [
                {
                    "type": "summary",
                    "title": "Overview",
                    "source_hint": "summary",
                    "width": "full",
                },
                {
                    "type": "flow_diagram",
                    "title": "How it works",
                    "source_hint": "process_flow",
                    "width": "full",
                },
                {
                    "type": "sequence_diagram",
                    "title": "Worked example",
                    "source_hint": "interaction_sequence",
                    "width": "full",
                },
                {
                    "type": "key_points",
                    "title": "Highlights",
                    "source_hint": "key_points",
                    "width": "half",
                },
            ],
        },
        goal="explain event loop in javascript",
    )
    assert out["presentation_profile"] == "mechanism_explainer"
    types = [b["type"] for b in out["block_outline"]]
    assert types == ["summary", "flow_diagram", "sequence_diagram"]
    # Digest blocks must not appear on explain goals even if extract filled them
    assert "key_points" not in types
    assert "faq" not in types
    assert "steps" not in types
    assert "chips" not in types


def test_mechanism_plan_strips_digest_blocks():
    structured = {
        "summary": "Event loop overview.",
        "key_points": ["a", "b", "c"],
        "faq": [{"question": "Q?", "answer": "A"}],
        "ordered_actions": ["Step 1", "Step 2"],
        "themes": ["js", "async"],
        "concepts": ["Call stack — LIFO frames"],
        "process_flow": {
            "nodes": [
                {"id": "a", "label": "Call Stack"},
                {"id": "b", "label": "Web APIs"},
            ],
            "edges": [{"source": "a", "target": "b", "label": "async"}],
        },
        "interaction_sequence": {
            "actors": ["Call Stack", "Web APIs"],
            "messages": [
                {
                    "source": "Call Stack",
                    "target": "Web APIs",
                    "label": "setTimeout",
                    "order": 0,
                }
            ],
        },
    }
    plan = {
        "presentation_profile": "mechanism_explainer",
        "block_outline": [
            {"type": "summary", "source_hint": "summary", "title": "Overview"},
            {"type": "key_points", "source_hint": "key_points", "title": "Highlights"},
            {"type": "faq", "source_hint": "faq", "title": "FAQ"},
            {"type": "steps", "source_hint": "ordered_actions", "title": "Steps"},
            {"type": "chips", "source_hint": "themes", "title": "Themes"},
            {"type": "flow_diagram", "source_hint": "process_flow", "title": "Flow"},
            {
                "type": "sequence_diagram",
                "source_hint": "interaction_sequence",
                "title": "Seq",
            },
            {"type": "key_terms", "source_hint": "concepts", "title": "Terms"},
        ],
    }
    out = stabilize_layout_plan(
        plan, structured=structured, goal="explain event loop in javascript"
    )
    types = [b["type"] for b in out["block_outline"]]
    assert types == [
        "summary",
        "flow_diagram",
        "sequence_diagram",
        "key_terms",
    ]


def test_stabilize_hub_topology_dropped_when_leaves_remain_connected():
    structured = {
        "process_flow": {
            "nodes": [
                {"id": "event_loop", "label": "Event Loop"},
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "c", "label": "C"},
            ],
            "edges": [
                {"source": "event_loop", "target": "a", "label": "x"},
                {"source": "event_loop", "target": "b", "label": "y"},
                {"source": "event_loop", "target": "c", "label": "z"},
                {"source": "a", "target": "b", "label": "handoff"},
            ],
        }
    }
    out = stabilize_process_flow_topology(structured)
    ids = {n["id"] for n in out["process_flow"]["nodes"]}
    assert "event_loop" not in ids
    assert "a" in ids and "b" in ids
    assert any(
        e["source"] == "a" and e["target"] == "b" for e in out["process_flow"]["edges"]
    )


def test_payload_from_assembly_sanitizes_profile():
    structured = {
        "summary": "Overview text for the event loop.",
        "key_points": ["One", "Two"],
        "process_flow": {
            "nodes": [
                {"id": "a", "label": "Call Stack", "detail": "LIFO"},
                {"id": "b", "label": "Web APIs", "detail": "timers"},
            ],
            "edges": [{"source": "a", "target": "b", "label": "async"}],
        },
    }
    layout = {
        "presentation_profile": "short_snake_case",
        "block_outline": [
            {"type": "summary", "title": "Overview", "source_hint": "summary"},
            {
                "type": "flow_diagram",
                "title": "How it works",
                "source_hint": "process_flow",
            },
        ],
    }
    payload = payload_from_assembly(
        layout_plan=layout,
        structured=structured,
        goal="explain event loop",
    )
    assert payload is not None
    assert payload["presentation_profile"] == "mechanism_explainer"
    assert "short" not in payload["presentation_profile"]
