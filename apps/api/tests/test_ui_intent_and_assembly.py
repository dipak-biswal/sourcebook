"""UiIntent skeleton + code assembly for Visual Summary."""

import uuid
from unittest.mock import MagicMock

from app.agents.visual_tools import _plan_with_validation
from app.presentation.context import PresentationContext
from app.presentation.engine import build_presentation
from app.presentation.evidence import AgentEvidenceBundle
from app.presentation.render_blocks import assemble_blocks, payload_from_assembly
from app.presentation.ui_intent import (
    build_skeleton_layout_plan,
    resolve_ui_intent,
)


LEARNING_PACKET = {
    "derived": {
        "outcome_phrase": "understand concepts and design systems",
        "success_criteria": "explain tradeoffs",
        "tone": "instructional",
        "visual_affordances": [
            "overview",
            "concept_glossary",
            "ordered_guide",
            "comparison_matrix",
            "self_check",
            "topic_filter",
        ],
    }
}

CAREER_PACKET = {
    "derived": {
        "outcome_phrase": "improve application materials",
        "success_criteria": "clear checklist",
        "tone": "analytical",
        "visual_affordances": [
            "overview",
            "priority_alert",
            "comparison_matrix",
            "qualitative_levels",
            "ordered_guide",
            "self_check",
        ],
    }
}


def test_learning_and_career_intents_differ():
    learning_struct = {
        "summary": "A distributed system is multiple nodes cooperating.",
        "key_points": ["Partial failure is normal", "Pick consistency per use case"],
        "faq": [{"question": "Stronger consistency always better?", "answer": "No."}],
        "sections": [
            {
                "heading": "Design process",
                "bullets": ["Requirements", "API", "Data model", "Diagram"],
            }
        ],
        "themes": ["fundamentals", "consistency", "scaling"],
    }
    career_struct = {
        "summary": "Strong React evidence; cloud keywords are thin.",
        "key_points": [
            "React | Strong",
            "AWS | Gap",
            "Use standard headings",
        ],
        "faq": [{"question": "Keyword stuffing?", "answer": "No."}],
        "sections": [
            {
                "heading": "Update checklist",
                "bullets": ["Add Skills line", "Rewrite top bullets", "Export plain PDF"],
            }
        ],
        "themes": ["keywords", "formatting"],
        "matrix_rows": [
            "Requirement | Evidence | Status",
            "React | Lead role | Strong",
            "AWS | Mentioned once | Gap",
        ],
        "levels": ["React | Strong", "AWS | Gap"],
    }

    li = resolve_ui_intent(
        structured_content=learning_struct,
        workspace_packet=LEARNING_PACKET,
        goal="What is a distributed system?",
    )
    ci = resolve_ui_intent(
        structured_content=career_struct,
        workspace_packet=CAREER_PACKET,
        goal="Make my resume ATS-friendly",
    )
    assert "concept_glossary" in li.block_order or "ordered_guide" in li.block_order
    assert "comparison_matrix" in ci.block_order or "ordered_guide" in ci.block_order
    assert li.block_order != ci.block_order


def test_skeleton_uses_source_hint_and_workspace_derived_profile():
    structured = {
        "summary": "Overview text.",
        "key_points": ["A", "B"],
        "faq": [{"question": "Q?", "answer": "A."}],
        "themes": ["a", "b"],
        "sections": [],
    }
    intent = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=LEARNING_PACKET,
        goal="Explain the topic",
    )
    plan = build_skeleton_layout_plan(intent, structured_content=structured)
    assert plan["presentation_profile"] == "workspace_derived"
    assert plan["block_outline"]
    assert all(b.get("source_hint") for b in plan["block_outline"])


def test_assemble_blocks_maps_source_hints():
    structured = {
        "summary": "Hello summary.",
        "key_points": ["Point one", "Point two"],
        "faq": [{"question": "Why?", "answer": "Because."}],
        "themes": ["alpha", "beta"],
        "sections": [{"heading": "How", "bullets": ["Step 1", "Step 2", "Step 3"]}],
    }
    outline = [
        {"type": "summary", "title": "Overview", "source_hint": "summary"},
        {"type": "key_points", "title": "Highlights", "source_hint": "key_points"},
        {"type": "steps", "title": "Steps", "source_hint": "ordered_actions"},
        {"type": "faq", "title": "FAQ", "source_hint": "faq"},
        {"type": "chips", "title": "Themes", "source_hint": "themes"},
        {"type": "progress", "title": "Levels", "source_hint": "levels"},
    ]
    blocks, dropped = assemble_blocks(outline, structured)
    types = [b.type for b in blocks]
    assert "summary" in types
    assert "key_points" in types
    assert "steps" in types
    assert "faq" in types
    assert "chips" in types
    assert any(d["type"] == "progress" for d in dropped)


def test_assembly_drops_degenerate_blocks():
    """Thin blocks (1-row table, single-item list, level-less progress) are dropped."""
    structured = {
        "summary": "A short but real overview of the workspace.",
        "key_points": ["Only one point"],
        "matrix_rows": ["Requirement | Evidence | Status"],  # header, no data rows
        "levels": ["No pipe here so no level"],
        "themes": ["solo"],  # only one theme → not enough for chips
    }
    outline = [
        {"type": "summary", "source_hint": "summary"},
        {"type": "key_points", "source_hint": "key_points"},
        {"type": "table", "source_hint": "matrix_rows"},
        {"type": "progress", "source_hint": "levels"},
        {"type": "chips", "source_hint": "themes"},
    ]
    blocks, dropped = assemble_blocks(outline, structured)
    types = [b.type for b in blocks]
    assert types == ["summary"]
    dropped_types = {d["type"] for d in dropped}
    assert {"key_points", "table", "progress", "chips"} <= dropped_types


def test_assembled_blocks_carry_width_hint():
    structured = {
        "summary": "Overview of the workspace materials for the reader.",
        "key_points": ["Point one", "Point two", "Point three"],
        "themes": ["alpha", "beta"],
    }
    outline = [
        {"type": "summary", "source_hint": "summary"},
        {"type": "key_points", "source_hint": "key_points"},
        {"type": "chips", "source_hint": "themes"},
    ]
    blocks, _ = assemble_blocks(outline, structured)
    by_type = {b.type: b for b in blocks}
    assert by_type["summary"].width == "full"
    assert by_type["chips"].width == "full"
    assert by_type["key_points"].width == "half"


def test_assemble_flow_diagram_from_process_flow():
    structured = {
        "process_flow": {
            "nodes": [
                {"id": "call_stack", "label": "Call Stack", "detail": "e.g. foo() runs"},
                {"id": "web_api", "label": "Web APIs", "detail": ""},
                {"id": "queue", "label": "Callback Queue", "detail": ""},
            ],
            "edges": [
                {"source": "call_stack", "target": "web_api", "label": "setTimeout"},
                {"source": "web_api", "target": "queue", "label": "callback ready"},
                {"source": "queue", "target": "call_stack", "label": "event loop tick"},
            ],
        },
    }
    outline = [{"type": "flow_diagram", "title": "How it works", "source_hint": "process_flow"}]
    blocks, dropped = assemble_blocks(outline, structured)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "flow_diagram"
    assert len(block.nodes) == 3
    assert len(block.edges) == 3
    assert block.nodes[0].detail == "e.g. foo() runs"
    assert not dropped


def test_assemble_flow_diagram_drops_edge_to_unknown_node():
    structured = {
        "process_flow": {
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "a", "target": "missing"},
            ],
        },
    }
    outline = [{"type": "flow_diagram", "source_hint": "process_flow"}]
    blocks, _ = assemble_blocks(outline, structured)
    assert len(blocks) == 1
    assert len(blocks[0].edges) == 1


def test_assemble_flow_diagram_empty_is_dropped():
    outline = [{"type": "flow_diagram", "source_hint": "process_flow"}]
    blocks, dropped = assemble_blocks(outline, {"process_flow": {"nodes": [], "edges": []}})
    assert not blocks
    assert dropped and dropped[0]["type"] == "flow_diagram"


def test_assemble_sequence_diagram_from_interaction_sequence():
    structured = {
        "interaction_sequence": {
            "actors": ["Call Stack", "Web APIs", "Callback Queue", "Event Loop"],
            "messages": [
                {"source": "Call Stack", "target": "Web APIs", "label": "setTimeout()", "order": 0},
                {"source": "Web APIs", "target": "Callback Queue", "label": "enqueue", "order": 1},
                {
                    "source": "Callback Queue",
                    "target": "Call Stack",
                    "label": "loop tick",
                    "order": 2,
                    "note": "Runs once stack is empty",
                },
            ],
        },
    }
    outline = [{"type": "sequence_diagram", "title": "Sequence", "source_hint": "interaction_sequence"}]
    blocks, dropped = assemble_blocks(outline, structured)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.type == "sequence_diagram"
    assert len(block.actors) == 4
    assert len(block.messages) == 3
    assert block.messages[2].note == "Runs once stack is empty"
    assert not dropped


def test_assemble_sequence_diagram_too_few_actors_dropped():
    structured = {
        "interaction_sequence": {
            "actors": ["Only One"],
            "messages": [{"source": "Only One", "target": "Only One", "label": "noop", "order": 0}],
        },
    }
    outline = [{"type": "sequence_diagram", "source_hint": "interaction_sequence"}]
    blocks, dropped = assemble_blocks(outline, structured)
    assert not blocks
    assert dropped and dropped[0]["type"] == "sequence_diagram"


def test_available_source_hints_includes_diagram_fields():
    from app.presentation.ui_intent import available_source_hints

    structured = {
        "summary": "Event loop overview",
        "process_flow": {
            "nodes": [
                {"id": "stack", "label": "Call Stack"},
                {"id": "queue", "label": "Task Queue"},
            ],
            "edges": [{"source": "stack", "target": "queue", "label": "async"}],
        },
        "interaction_sequence": {
            "actors": ["Stack", "Queue"],
            "messages": [
                {
                    "source": "Stack",
                    "target": "Queue",
                    "label": "enqueue",
                    "order": 0,
                }
            ],
        },
    }
    present = available_source_hints(structured)
    assert "process_flow" in present
    assert "interaction_sequence" in present


def test_explain_goal_leads_with_mechanism_when_process_flow_present():
    from app.presentation.ui_intent import resolve_ui_intent

    structured = {
        "summary": "The event loop runs async callbacks when the stack is clear.",
        "key_points": ["JS is single-threaded", "Queues hold callbacks"],
        "concepts": ["Event loop — scheduler", "Call stack — frames"],
        "faq": [{"question": "Is JS multi-threaded?", "answer": "No."}],
        "process_flow": {
            "nodes": [
                {"id": "stack", "label": "Call Stack", "detail": "Sync frames"},
                {"id": "web", "label": "Web APIs"},
                {"id": "queue", "label": "Callback Queue"},
            ],
            "edges": [
                {"source": "stack", "target": "web", "label": "setTimeout"},
                {"source": "web", "target": "queue", "label": "ready"},
                {"source": "queue", "target": "stack", "label": "tick"},
            ],
        },
    }
    intent = resolve_ui_intent(
        structured_content=structured,
        workspace_packet={
            "derived": {
                "visual_affordances": [
                    "mechanism_explainer",
                    "concept_glossary",
                    "self_check",
                ]
            }
        },
        goal="explain eventloop",
    )
    # Teaching outline: overview + mechanism diagrams (no FAQ/steps/highlights).
    assert intent.block_order[0] in ("overview", "mechanism_explainer")
    assert "mechanism_explainer" in intent.block_order
    assert "highlights" not in intent.block_order
    assert "self_check" not in intent.block_order
    assert "ordered_guide" not in intent.block_order

    plan = build_skeleton_layout_plan(intent, structured_content=structured)
    types = [b["type"] for b in plan.get("block_outline") or []]
    assert "flow_diagram" in types
    assert "key_points" not in types
    assert "faq" not in types
    assert types.index("flow_diagram") <= 2


def test_goal_aware_lead_block_for_comparison():
    structured = {
        "summary": "React is strong; cloud is thin.",
        "key_points": ["Quantify impact", "Add a skills line"],
        "matrix_rows": [
            "Requirement | Evidence | Status",
            "React | Lead role | Strong",
            "AWS | Once | Gap",
        ],
        "themes": ["frontend", "cloud"],
    }
    intent = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=CAREER_PACKET,
        goal="Compare my React vs AWS readiness",
    )
    plan = build_skeleton_layout_plan(intent, structured_content=structured)
    assert plan["block_outline"][0]["type"] == "table"


def test_plan_layout_uses_code_skeleton_without_llm(monkeypatch):
    monkeypatch.setattr(
        "app.agents.visual_tools.settings.visual_summary_llm_planner", False
    )
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Explain the notes",
        final_answer="Enough answer text for presentation.",
        structured_content={
            "summary": "Summary body for the visual.",
            "key_points": ["One", "Two"],
            "faq": [],
            "sections": [],
            "themes": [],
        },
        workspace_packet=LEARNING_PACKET,
        agent_evidence=AgentEvidenceBundle(),
    )
    result = _plan_with_validation(ctx)
    assert result["validation_status"] == "passed"
    assert result["replan_attempted"] is False
    assert result["usage"]["model"] == "code_skeleton"
    assert result["plan"]["presentation_profile"] == "workspace_derived"
    assert result["plan"]["block_outline"]


def test_build_presentation_assembly_skips_llm():
    structured = {
        "summary": "Overview of the workspace materials.",
        "key_points": ["Shipped RAG", "TypeScript and Python"],
        "faq": [{"question": "What stack?", "answer": "React and FastAPI."}],
        "sections": [],
        "themes": ["rag", "stack"],
    }
    layout_plan = {
        "presentation_profile": "workspace_derived",
        "components": ["summary", "key_points", "faq", "chips"],
        "block_outline": [
            {"type": "summary", "title": "Overview", "source_hint": "summary"},
            {"type": "key_points", "title": "Highlights", "source_hint": "key_points"},
            {"type": "faq", "title": "FAQ", "source_hint": "faq"},
            {"type": "chips", "title": "Themes", "source_hint": "themes"},
        ],
        "rationale": "test",
    }
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize with key points and FAQ",
        final_answer="Long enough answer for presentation path validation checks here.",
        structured_content=structured,
        layout_plan=layout_plan,
        workspace_name="Study",
        agent_evidence=AgentEvidenceBundle(),
    )
    # If LLM is called, this will raise
    db = MagicMock()
    spec, meta = build_presentation(db, ctx)
    assert spec.get("error") is None
    assert meta["model"] == "code_assembly"
    types = [b["type"] for b in spec.get("blocks") or []]
    assert "summary" in types
    assert "key_points" in types
    assert meta.get("assembly_meta", {}).get("render_fallback_used") is False


def test_payload_from_assembly_none_when_empty():
    assert (
        payload_from_assembly(
            layout_plan={"block_outline": [{"type": "progress", "source_hint": "levels"}]},
            structured={"summary": "", "key_points": [], "faq": []},
            goal="x",
        )
        is None
    )


def test_job_search_assembly_splits_levels_and_matrix():
    structured = {
        "summary": "Strong React; cloud keywords are thin.",
        "key_points": [
            "Use standard headings",
            "React | Strong",
            "AWS | Gap",
            "CI/CD | Gap",
        ],
        "faq": [{"question": "Keyword stuffing?", "answer": "No."}],
        "sections": [
            {
                "heading": "Update checklist",
                "bullets": ["Add Skills line", "Rewrite bullets", "Export PDF"],
            },
            {
                "heading": "Mapping",
                "bullets": [
                    "Requirement | Evidence | Status",
                    "React | 8 years | Strong",
                    "AWS | Once | Gap",
                ],
            },
        ],
        "themes": ["keywords", "formatting"],
    }
    plan = build_skeleton_layout_plan(
        resolve_ui_intent(
            structured_content=structured,
            workspace_packet=CAREER_PACKET,
            goal="Make resume ATS-friendly",
        ),
        structured_content=structured,
    )
    payload = payload_from_assembly(
        layout_plan=plan,
        structured=structured,
        goal="Make resume ATS-friendly",
        workspace_name="Job Search",
    )
    assert payload
    by_type = {b["type"]: b for b in payload["blocks"]}
    # Key points should not be polluted with Strong/Gap rows
    if "key_points" in by_type:
        for item in by_type["key_points"].get("items") or []:
            assert " | Strong" not in item and " | Gap" not in item
    # Table rows should be consistent 3-col matrix, not mixed 2-col levels
    if "table" in by_type:
        rows = by_type["table"].get("items") or []
        assert rows
        col_counts = {len([c for c in r.split("|")]) for r in rows}
        assert len(col_counts) == 1
        assert next(iter(col_counts)) == 3
    # Progress should capture qualitative levels when present
    if "progress" in by_type:
        assert any("Strong" in (i or "") or "Gap" in (i or "") for i in (by_type["progress"].get("items") or []))
    assert plan["block_outline"][0]["type"] == "summary"


def test_steps_dedupe_labels_and_key_points_overlap():
    structured = {
        "summary": "Improve your resume with these steps:",
        "key_points": [
            "Identify key skills for the role.",
            "Quantify your impact with metrics.",
        ],
        "ordered_actions": [
            "Analyze Job Descriptions:",  # label marker, should be dropped
            "Identify key skills for the role.",
            "Quantify your impact with metrics.",
            "Set a timeline for each step.",
        ],
        "themes": [],
    }
    outline = [
        {"type": "steps", "source_hint": "ordered_actions"},
        {"type": "key_points", "source_hint": "key_points"},
        {"type": "summary", "source_hint": "summary"},
    ]
    blocks, dropped = assemble_blocks(outline, structured)
    by_type = {b.type: b for b in blocks}
    # Label marker removed from steps
    assert "Analyze Job Descriptions:" not in (by_type["steps"].items or [])
    # key_points fully overlaps steps -> dropped as duplicate
    assert "key_points" not in by_type
    assert any(d.get("reason") == "duplicates steps" for d in dropped)
    # Colon lead-in is not used as the summary body
    assert not (by_type["summary"].body or "").endswith(
        "Improve your resume with these steps:"
    )


def test_callout_not_fabricated_and_faq_requires_real_answer():
    structured = {
        "summary": "A normal overview sentence about the workspace.",
        "priority_message": "",
        "gaps": [],
        "faq": [
            {
                "question": "Is my resume tailored?",
                "answer": "Have I quantified impact? - Is it error-free?",  # questions only
            }
        ],
    }
    outline = [
        {"type": "callout", "source_hint": "priority_message"},
        {"type": "faq", "source_hint": "faq"},
    ]
    blocks, _ = assemble_blocks(outline, structured)
    types = {b.type for b in blocks}
    assert "callout" not in types  # no real priority -> not fabricated from summary
    assert "faq" not in types  # question-only answer rejected


def test_blocks_tagged_from_themes_for_chip_filtering():
    structured = {
        "summary": "React skills are strong; feedback loops need work.",
        "key_points": [
            "React component architecture is a strength.",
            "Collect feedback from senior peers regularly.",
        ],
        "themes": ["react", "feedback"],
    }
    outline = [
        {"type": "summary", "source_hint": "summary"},
        {"type": "key_points", "source_hint": "key_points"},
        {"type": "chips", "source_hint": "themes"},
    ]
    blocks, _ = assemble_blocks(outline, structured)
    by_type = {b.type: b for b in blocks}
    # Non-chips blocks carry the themes they mention as tags.
    assert "react" in (by_type["summary"].tags or [])
    assert "feedback" in (by_type["key_points"].tags or [])
    # The chips block itself stays untagged.
    assert not by_type["chips"].tags
