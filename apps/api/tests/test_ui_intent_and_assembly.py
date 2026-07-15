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


def test_plan_layout_uses_code_skeleton_without_llm():
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
