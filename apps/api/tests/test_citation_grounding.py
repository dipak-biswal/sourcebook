"""Real citation IDs on sources and domain-agnostic grounding fallbacks."""

import uuid

from app.visual_summary.blocks.gen_ui import GenUIBlock
from app.visual_summary.context import PresentationContext
from app.visual_summary.render.engine import (
    _attribute_block_sources,
    _ensure_requested_layout,
    _infer_qualitative_level,
    build_presentation,
)
from app.visual_summary.handoff.evidence import (
    AgentEvidenceBundle,
    DocumentEvidenceHit,
    collect_evidence_from_steps,
    serialize_agent_evidence,
)
from app.visual_summary.blocks.gen_ui import SourceSnippet


# --- #6: evidence carries document_id end to end ---


def test_collect_evidence_parses_document_id():
    steps = [
        {
            "step_index": 1,
            "type": "tool_result",
            "tool_name": "search_documents",
            "output": [
                {
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "filename": "Spec.pdf",
                    "snippet": "Latency budget is 200ms for the search endpoint.",
                    "score": 0.88,
                }
            ],
        },
    ]
    bundle = collect_evidence_from_steps(steps)
    hit = bundle.document_hits[0]
    assert hit.document_id == "d1"
    assert hit.chunk_id == "c1"
    serialized = serialize_agent_evidence(bundle)
    assert serialized["document_hits"][0]["document_id"] == "d1"


def test_build_presentation_sources_carry_real_ids(monkeypatch):
    class FakeDB:
        def commit(self):
            pass

    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize the spec",
        final_answer=(
            "The latency budget is 200ms for the search endpoint. "
            "Deployment uses blue-green rollouts."
        ),
        structured_content={
            "summary": "Latency budget is 200ms; deployment uses blue-green rollouts.",
            "key_points": ["Latency budget 200ms", "Blue-green deployment"],
            "faq": [],
            "sections": [],
        },
        layout_plan={
            "presentation_profile": "workspace_derived",
            "components": ["summary"],
            "block_outline": [
                {"type": "summary", "title": "Overview", "source_hint": "summary"},
            ],
        },
        agent_evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(
                    filename="Spec.pdf",
                    snippet="Latency budget is 200ms for the search endpoint.",
                    score=0.88,
                    chunk_id="c1",
                    document_id="d1",
                )
            ]
        ),
    )
    spec, _meta = build_presentation(FakeDB(), ctx)
    assert not spec.get("error"), spec
    src = spec["sources"][0]
    assert src["chunk_id"] == "c1"
    assert src["document_id"] == "d1"
    assert src["score"] == 0.88


# --- #6: overlap-based source attribution for assembly blocks ---


def _sources():
    return [
        SourceSnippet(
            index=1,
            chunk_id="c1",
            document_id="d1",
            filename="Spec.pdf",
            score=0.9,
            snippet="Latency budget is 200ms for the search endpoint under load.",
        ),
        SourceSnippet(
            index=2,
            chunk_id="c2",
            document_id="d1",
            filename="Spec.pdf",
            score=0.8,
            snippet="Deployment uses blue-green rollouts with automated canary checks.",
        ),
    ]


def test_attribution_attaches_overlapping_source():
    blocks = [
        GenUIBlock(
            type="summary",
            title="Overview",
            body="The latency budget is 200ms for the search endpoint.",
        )
    ]
    out = _attribute_block_sources(blocks, _sources())
    assert out[0].source_indices == [1]


def test_attribution_leaves_unrelated_block_uncited():
    blocks = [
        GenUIBlock(
            type="summary",
            title="Team",
            body="Weekly sync happens each Monday morning with rotating notes.",
        )
    ]
    out = _attribute_block_sources(blocks, _sources())
    assert out[0].source_indices == []


def test_attribution_preserves_existing_indices():
    blocks = [
        GenUIBlock(
            type="summary",
            body="Latency budget is 200ms for the search endpoint.",
            source_indices=[2],
        )
    ]
    out = _attribute_block_sources(blocks, _sources())
    assert out[0].source_indices == [2]


# --- #5: no fabricated chips; generic qualitative levels ---


def test_chips_fallback_uses_structured_themes():
    out = _ensure_requested_layout(
        [],
        ["chips"],
        answer="Any answer text",
        structured={"themes": ["pricing", "compliance", "onboarding"]},
    )
    chips = [b for b in out if b.type == "chips"]
    assert len(chips) == 1
    assert chips[0].items == [
        "Pricing|pricing",
        "Compliance|compliance",
        "Onboarding|onboarding",
    ]


def test_chips_fallback_omitted_without_themes():
    out = _ensure_requested_layout(
        [],
        ["chips"],
        answer="Any answer text",
        structured={},
    )
    assert not any(b.type == "chips" for b in out)


def test_existing_chips_not_padded_with_invented_tags():
    chips = GenUIBlock(type="chips", title="Themes", items=["Pricing|pricing"])
    out = _ensure_requested_layout(
        [chips],
        ["chips"],
        answer="Any answer",
        structured={},
    )
    assert out[0].items == ["Pricing|pricing"]


def test_qualitative_level_generic_domain():
    answer = (
        "Vendor onboarding remains a gap — contracts stall in legal review. "
        "Invoice processing is strong after automation. "
        "Compliance reporting is improving with the new dashboard."
    )
    assert _infer_qualitative_level("Vendor Onboarding", answer) == "Gap"
    assert _infer_qualitative_level("Invoice Processing", answer) == "Strong"
    assert _infer_qualitative_level("Compliance Reporting", answer) == "Growing"
    assert _infer_qualitative_level("Unmentioned Area", answer) == "Moderate"
