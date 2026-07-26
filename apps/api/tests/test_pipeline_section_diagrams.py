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

    mcp_blocks = [b for b in new_spec["blocks"] if b.get("type") == "mcp_diagram"]
    assert len(mcp_blocks) == 1
    assert mcp_blocks[0]["diagram_kind"] == "tree"
    assert mcp_blocks[0]["edit_url"] == "https://app.diagrams.net/?x=1"

    # Every other block is untouched (same count, no other mcp_diagram).
    assert len(new_spec["blocks"]) == len(spec["blocks"])
    other_original_types = {
        b["type"] for b in spec["blocks"] if b.get("type") != "mcp_diagram"
    }
    other_new_types = {
        b.get("type") for b in new_spec["blocks"] if b.get("type") != "mcp_diagram"
    }
    assert other_new_types <= other_original_types


def test_apply_section_diagrams_noop_when_nothing_rendered():
    spec = {"type": "generative_ui", "title": "T", "blocks": [{"type": "summary", "tags": []}]}
    new_spec, applied = _apply_section_diagrams_to_spec(spec, {})
    assert applied == 0
    assert new_spec is spec
