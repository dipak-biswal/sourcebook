"""draw.io MCP connector helpers for visual summary."""

from app.mcp.drawio import (
    attach_drawio_to_spec,
    drawio_edit_url,
    enabled_mcp_ids_from_run,
    mermaid_from_structured,
    run_drawio_mcp_for_visual,
)


def test_mermaid_from_process_flow():
    structured = {
        "process_flow": {
            "nodes": [
                {"id": "a", "label": "Start"},
                {"id": "b", "label": "End"},
            ],
            "edges": [{"from": "a", "to": "b", "label": "go"}],
        }
    }
    mermaid, kind = mermaid_from_structured(structured)
    assert kind == "flowchart"
    assert mermaid is not None
    assert "flowchart TD" in mermaid
    assert "Start" in mermaid
    assert "-->" in mermaid


def test_mermaid_from_sequence():
    structured = {
        "interaction_sequence": {
            "actors": [{"name": "Client"}, {"name": "API"}],
            "messages": [
                {"from": "Client", "to": "API", "message": "request"},
            ],
        }
    }
    mermaid, kind = mermaid_from_structured(structured)
    assert kind == "sequence"
    assert mermaid is not None
    assert "sequenceDiagram" in mermaid
    assert "Client" in mermaid


def test_run_drawio_goal_fallback_when_thin_structure():
    result = run_drawio_mcp_for_visual(
        structured={"summary": "hi"},
        goal="Explain the pipeline",
        try_npx=False,
    )
    assert result["status"] == "ok"
    assert "mermaid" in result


def test_run_drawio_from_presentation_blocks():
    spec = {
        "type": "generative_ui",
        "title": "T",
        "blocks": [
            {
                "type": "flow_diagram",
                "nodes": [
                    {"id": "a", "label": "Ingest"},
                    {"id": "b", "label": "Answer"},
                ],
                "edges": [{"from": "a", "to": "b"}],
            }
        ],
    }
    result = run_drawio_mcp_for_visual(
        structured={},
        presentation_spec=spec,
        try_npx=False,
    )
    assert result["status"] == "ok"
    assert "Ingest" in result["mermaid"]


def test_run_drawio_ok_with_flow(monkeypatch):
    structured = {
        "process_flow": {
            "nodes": [{"id": "1", "label": "A"}, {"id": "2", "label": "B"}],
            "edges": [{"from": "1", "to": "2"}],
        }
    }

    def _fake_png(mermaid: str):
        assert "flowchart" in mermaid
        return {
            "png_url": "https://example.test/diagram.png",
            "png_data_url": "data:image/png;base64,AAAA",
            "png_bytes": 4,
            "embedded": True,
        }

    monkeypatch.setattr(
        "app.mcp.drawio.render_mermaid_png",
        _fake_png,
    )
    result = run_drawio_mcp_for_visual(
        structured=structured, goal="Explain pipeline", try_npx=False
    )
    assert result["status"] == "ok"
    assert result["edit_url"].startswith("https://app.diagrams.net/")
    assert "mermaid" in result
    assert "create=" in result["edit_url"]
    assert result["png_data_url"] == "data:image/png;base64,AAAA"
    assert result["preview_url"] == "data:image/png;base64,AAAA"


def test_attach_drawio_to_spec():
    spec = {"type": "generative_ui", "title": "T", "blocks": []}
    result = {
        "status": "ok",
        "mermaid": "flowchart TD\n  a-->b",
        "edit_url": "https://app.diagrams.net/?x=1",
        "preview_url": "https://mermaid.ink/svg/x",
        "diagram_kind": "flowchart",
    }
    out = attach_drawio_to_spec(spec, result)
    assert out["meta"]["drawio"]["edit_url"] == result["edit_url"]


def test_enabled_mcp_ids_from_run():
    class R:
        run_options = {"enabled_mcp_ids": ["mcp_drawio", " other "]}

    assert enabled_mcp_ids_from_run(R()) == ["mcp_drawio", "other"]


def test_drawio_edit_url_encodes_mermaid():
    url = drawio_edit_url("flowchart TD\n  a-->b", title="Demo")
    assert "app.diagrams.net" in url
    assert "create=" in url


def test_attach_includes_png_data_url():
    from app.mcp.drawio import attach_drawio_to_spec

    spec = {"type": "generative_ui", "title": "T", "blocks": []}
    out = attach_drawio_to_spec(
        spec,
        {
            "status": "ok",
            "mermaid": "flowchart TD\n  a-->b",
            "edit_url": "https://app.diagrams.net/?x=1",
            "png_data_url": "data:image/png;base64,QQ==",
            "png_url": "https://example.test/a.png",
            "diagram_kind": "flowchart",
        },
    )
    assert out["meta"]["drawio"]["png_data_url"].startswith("data:image/png")
    assert out["meta"]["drawio"]["preview_url"].startswith("data:image/png")
