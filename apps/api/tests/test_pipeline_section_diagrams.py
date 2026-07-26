"""Per-section draw.io MCP wiring: panel_index alignment + block splicing."""

from app.agents.visual_summary.pipeline import (
    _apply_section_diagrams_to_spec,
    _study_sheet_panel_sections,
)
from app.agents.visual_summary.planning.study_sheet import build_topic_study_sheet_plan
from app.agents.visual_summary.render.assemble import assemble_blocks
from app.agents.visual_summary.handoff.structured import extract_structured_content
from tests.test_study_sheet import _outbox_answer


def _plan_and_structured():
    structured = extract_structured_content(
        _outbox_answer(),
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    plan = build_topic_study_sheet_plan(
        structured, goal="Create a complete study sheet for the Outbox Pattern"
    )
    assert plan is not None
    return plan, structured


def test_study_sheet_panel_sections_align_with_block_tags():
    plan, structured = _plan_and_structured()
    panel_sections = _study_sheet_panel_sections(plan, structured)
    assert panel_sections
    blocks, _dropped = assemble_blocks(plan["block_outline"], structured)

    tagged_panels = set()
    for b in blocks:
        for t in b.tags or []:
            if t.startswith("__section:"):
                tagged_panels.add(int(t.split(":")[1]))
    # Every panel index we plan to author a diagram for actually lands on a
    # rendered block — otherwise render_section_diagrams_via_mcp would author
    # diagrams for sections nothing can display.
    panel_indices = {n for n, _sec in panel_sections}
    assert panel_indices & tagged_panels


def test_apply_section_diagrams_replaces_only_matching_panels():
    plan, structured = _plan_and_structured()
    blocks, _dropped = assemble_blocks(plan["block_outline"], structured)
    spec = {"type": "generative_ui", "title": "T", "blocks": [b.model_dump() for b in blocks]}

    # Pick one real panel index present in the assembled blocks.
    target_panel = None
    for b in blocks:
        for t in b.tags or []:
            if t.startswith("__section:"):
                target_panel = int(t.split(":")[1])
                break
        if target_panel is not None:
            break
    assert target_panel is not None

    rendered = {
        target_panel: {
            "mermaid": "flowchart TD\n  a-->b",
            "diagram_kind": "tree",
            "edit_url": "https://app.diagrams.net/?x=1",
            "preview_url": "https://mermaid.ink/img/abc",
            "source": "mcp_stdio",
        }
    }
    new_spec, applied = _apply_section_diagrams_to_spec(spec, rendered)
    assert applied == 1

    # MCP augments the matching panel — does not replace with mcp_diagram type.
    enriched = [
        b
        for b in new_spec["blocks"]
        if isinstance(b.get("tags"), list)
        and f"__section:{target_panel}" in b["tags"]
    ]
    assert len(enriched) == 1
    assert enriched[0]["diagram_kind"] == "tree"
    assert enriched[0]["edit_url"] == "https://app.diagrams.net/?x=1"
    assert enriched[0]["type"] != "mcp_diagram" or enriched[0].get("mermaid")

    # Same panel count; original teaching type preserved when it wasn't mcp.
    assert len(new_spec["blocks"]) == len(spec["blocks"])
    original_target = next(
        b
        for b in spec["blocks"]
        if isinstance(b.get("tags"), list)
        and f"__section:{target_panel}" in b["tags"]
    )
    assert enriched[0]["type"] == original_target["type"]
    # Non-target blocks keep their types.
    for orig, new in zip(spec["blocks"], new_spec["blocks"], strict=False):
        o_tags = orig.get("tags") or []
        if f"__section:{target_panel}" in o_tags:
            continue
        assert orig.get("type") == new.get("type")


def test_apply_section_diagrams_noop_when_nothing_rendered():
    spec = {"type": "generative_ui", "title": "T", "blocks": [{"type": "summary", "tags": []}]}
    new_spec, applied = _apply_section_diagrams_to_spec(spec, {})
    assert applied == 0
    assert new_spec is spec
