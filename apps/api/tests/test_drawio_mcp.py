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


def test_run_drawio_skips_without_structure():
    result = run_drawio_mcp_for_visual(structured={"summary": "hi"}, try_npx=False)
    assert result["status"] == "skipped"


def test_run_drawio_ok_with_flow():
    structured = {
        "process_flow": {
            "nodes": [{"id": "1", "label": "A"}, {"id": "2", "label": "B"}],
            "edges": [{"from": "1", "to": "2"}],
        }
    }
    result = run_drawio_mcp_for_visual(
        structured=structured, goal="Explain pipeline", try_npx=False
    )
    assert result["status"] == "ok"
    assert result["edit_url"].startswith("https://app.diagrams.net/")
    assert "mermaid" in result
    assert "create=" in result["edit_url"]


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
