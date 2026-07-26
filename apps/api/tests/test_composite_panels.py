"""Composite panels: prose + figure together; MCP augments rather than replaces."""

from app.agents.visual_summary.pipeline import _apply_section_diagrams_to_spec
from app.agents.visual_summary.render.assemble import assemble_blocks
from app.agents.visual_summary.streaming.progressive import merge_prose_into_figure


def test_merge_prose_into_figure_keeps_items():
    prose = {
        "type": "key_points",
        "title": "2. Flow",
        "items": ["Write DB", "Outbox", "Publish"],
        "tags": ["__section:2"],
    }
    figure = {
        "type": "flow_diagram",
        "title": "2. Flow",
        "nodes": [{"id": "a", "label": "DB"}, {"id": "b", "label": "Outbox"}],
        "edges": [{"source": "a", "target": "b"}],
    }
    out = merge_prose_into_figure(prose, figure)
    assert out["type"] == "flow_diagram"
    assert out["items"] == prose["items"]
    assert "__section:2" in (out.get("tags") or [])


def test_assemble_flow_diagram_includes_prose_items():
    structured = {
        "summary": "Outbox",
        "sections": [
            {
                "heading": "2. High Level Flow",
                "body": "A → B → C → D",
                "bullets": [
                    "Business operation first",
                    "Write to database",
                    "Write outbox row",
                ],
            }
        ],
        "key_points": [],
        "faq": [],
        "themes": [],
    }
    outline = [
        {
            "type": "flow_diagram",
            "title": "2. High Level Flow",
            "source_hint": "process_flow",
            "width": "full",
            "section_index": 1,
            "panel_index": 1,
        }
    ]
    blocks, _ = assemble_blocks(outline, structured)
    assert blocks
    b = blocks[0]
    assert b.type == "flow_diagram"
    assert b.nodes and len(b.nodes) >= 2
    assert b.items and len(b.items) >= 1


def test_mcp_enrich_does_not_replace_panel():
    spec = {
        "type": "generative_ui",
        "title": "T",
        "blocks": [
            {
                "type": "flow_diagram",
                "title": "2. Flow",
                "tags": ["__section:1"],
                "items": ["Keep me"],
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "edges": [{"source": "a", "target": "b"}],
            }
        ],
    }
    rendered = {
        1: {
            "mermaid": "flowchart LR\nA-->B",
            "diagram_kind": "flowchart",
            "png_data_url": "data:image/png;base64,xx",
            "edit_url": "https://app.diagrams.net/",
            "source": "local_fallback",
        }
    }
    new_spec, applied = _apply_section_diagrams_to_spec(spec, rendered)
    assert applied == 1
    b = new_spec["blocks"][0]
    assert b["type"] == "flow_diagram"
    assert b["items"] == ["Keep me"]
    assert b["mermaid"]
    assert b["png_data_url"]
    assert b["nodes"]
