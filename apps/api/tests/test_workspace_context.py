"""WorkspaceContextPacket derivation — no vertical enums in asserts."""

from app.presentation.workspace_context import (
    DERIVATION_VERSION,
    derive_workspace_context,
    format_main_agent_system_prompt,
    format_workspace_context_for_agent,
)


def test_empty_description_low_confidence_generic():
    packet = derive_workspace_context(
        name="Workspace 1",
        description=None,
        tags=None,
        document_rows=[],
    )
    assert packet.meta.confidence == "low"
    assert packet.meta.derivation_version == DERIVATION_VERSION
    assert "overview" in packet.derived.visual_affordances
    assert packet.derived.tool_policy.external_context_ok is True


def test_learning_description_derives_concepts_and_instructional_tone():
    packet = derive_workspace_context(
        name="Learn System Design",
        description=(
            "Study distributed systems from my notes. Help me understand concepts "
            "and design simple systems on my own. Audience: me. "
            "Success looks like: I can explain tradeoffs and sketch an architecture."
        ),
        tags=["course", "system-design"],
        document_rows=[("ddia-notes.pdf", "ready"), ("primer.md", "ready")],
    )
    assert packet.meta.confidence == "high"
    assert packet.derived.tone == "instructional"
    assert "concept_glossary" in packet.derived.visual_affordances
    assert "ordered_guide" in packet.derived.visual_affordances
    assert "mechanism_explainer" in packet.derived.visual_affordances
    assert "interaction_walkthrough" in packet.derived.visual_affordances
    assert "explain tradeoffs" in packet.derived.success_criteria.lower()
    assert len(packet.evidence.documents_ready) == 2
    assert "Core concepts" in packet.derived.answer_sections
    assert "How it works" in packet.derived.answer_sections


def test_comparison_description_derives_matrix_and_analytical():
    packet = derive_workspace_context(
        name="Job Search 2026",
        description=(
            "Prepare applications for senior full-stack roles. Compare my materials "
            "to job descriptions and guide prioritized updates. Success looks like: "
            "clear edit checklist per role."
        ),
        tags=["hiring"],
        document_rows=[("my-cv.pdf", "ready"), ("acme-jd.pdf", "ready")],
    )
    assert packet.meta.confidence == "high"
    assert packet.derived.tone == "analytical"
    assert "comparison_matrix" in packet.derived.visual_affordances
    assert "ordered_guide" in packet.derived.visual_affordances
    assert packet.derived.tool_policy.max_search_documents >= 2


def test_private_workspace_disables_web():
    packet = derive_workspace_context(
        name="Acme RFP",
        description="Confidential RFP response. Internal only — no web. Private bid materials.",
        tags=["legal"],
        document_rows=[("rfp.pdf", "ready")],
    )
    assert packet.derived.tool_policy.external_context_ok is False
    assert packet.derived.tool_policy.max_web_search == 0


def test_same_goal_different_workspaces_different_affordances():
    learning = derive_workspace_context(
        name="Learn System Design",
        description="Understand distributed systems concepts and design on my own.",
        tags=["course"],
        document_rows=[("notes.pdf", "ready")],
    )
    career = derive_workspace_context(
        name="Job Search",
        description="Compare materials to requirements and guide checklist updates for roles.",
        tags=["hiring"],
        document_rows=[("cv.pdf", "ready")],
    )
    assert learning.derived.visual_affordances != career.derived.visual_affordances
    assert "concept_glossary" in learning.derived.visual_affordances
    assert "comparison_matrix" in career.derived.visual_affordances


def test_format_agent_prompt_includes_workspace_and_no_resume_bias():
    packet = derive_workspace_context(
        name="Notes",
        description="Personal study notes for algorithms.",
        tags=["learning"],
        document_rows=[("algo.md", "ready")],
    )
    text = format_workspace_context_for_agent(packet)
    assert "WORKSPACE CONTEXT" in text
    assert "Notes" in text
    assert "algorithms" in text.lower()
    assert "resume" not in text.lower()

    composed = format_main_agent_system_prompt(
        "You are Sourcebook's workspace agent.",
        packet,
    )
    assert "WORKSPACE CONTEXT" in composed
    assert "You are Sourcebook's workspace agent." in composed


def test_packet_schema_has_no_vertical_enum_fields():
    packet = derive_workspace_context(
        name="X",
        description="Learn concepts and compare approaches.",
        tags=["research"],
        document_rows=[],
    )
    raw = packet.to_dict()
    assert "design_lab" not in str(raw)
    assert "career_lab" not in str(raw)
    assert "presentation_mode" not in raw.get("derived", {})
    assert "domain_hint" not in raw.get("derived", {})


def test_empty_workspace_gets_research_budgets():
    packet = derive_workspace_context(
        name="Fresh", description=None, tags=None, document_rows=[]
    )
    policy = packet.derived.tool_policy
    assert policy.external_context_ok is True
    assert policy.max_web_search == 3
    assert policy.max_fetch_url == 3
    text = format_workspace_context_for_agent(packet)
    assert "RESEARCH MODE" in text
    assert "fetch_url" in text


def test_corpus_workspace_gets_default_budgets():
    packet = derive_workspace_context(
        name="Docs",
        description="Team documentation corpus",
        tags=None,
        document_rows=[(f"doc{i}.txt", "ready") for i in range(5)],
    )
    policy = packet.derived.tool_policy
    assert policy.max_web_search == 1
    assert policy.max_fetch_url == 2
    assert "RESEARCH MODE" not in format_workspace_context_for_agent(packet)


def test_private_workspace_zeroes_web_and_fetch():
    packet = derive_workspace_context(
        name="Legal",
        description="Confidential contracts — private, no web lookups.",
        tags=None,
        document_rows=[],
    )
    policy = packet.derived.tool_policy
    assert policy.external_context_ok is False
    assert policy.max_web_search == 0
    assert policy.max_fetch_url == 0
    text = format_workspace_context_for_agent(packet)
    # Even with zero documents, private workspaces never enter research mode.
    assert "RESEARCH MODE" not in text
    assert "OFF" in text
