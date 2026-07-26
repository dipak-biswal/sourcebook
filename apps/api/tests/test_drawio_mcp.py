"""draw.io MCP connector helpers for visual summary."""

import pytest

from app.mcp.drawio import (
    attach_drawio_to_spec,
    call_drawio_mcp_open_mermaid,
    drawio_edit_url,
    enabled_mcp_ids_from_run,
    mermaid_from_structured,
    run_drawio_mcp_for_visual,
)
from app.mcp.stdio_client import extract_urls, parse_tool_text_content


@pytest.fixture(autouse=True)
def _disable_mcp_spawn_and_png(monkeypatch):
    """Unit tests must not spawn npx or hit mermaid.ink (slow / flaky)."""
    monkeypatch.setattr("app.mcp.drawio._mcp_process_enabled", lambda: False)
    monkeypatch.setattr(
        "app.mcp.drawio.render_mermaid_png",
        lambda mermaid: {
            "png_url": "https://example.test/diagram.png",
            "png_data_url": "data:image/png;base64,AAAA",
            "png_bytes": 4,
            "embedded": True,
        },
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
        structured=structured, goal="Explain pipeline"
    )
    assert result["status"] == "ok"
    assert result["edit_url"].startswith("https://app.diagrams.net/")
    assert "mermaid" in result
    assert "create=" in result["edit_url"]
    assert result["png_data_url"] == "data:image/png;base64,AAAA"
    assert result["preview_url"] == "data:image/png;base64,AAAA"
    # Spawn disabled → local fallback path
    assert result["source"] == "local_fallback"


def test_run_drawio_uses_mcp_url_when_stdio_ok(monkeypatch):
    structured = {
        "process_flow": {
            "nodes": [{"id": "1", "label": "A"}, {"id": "2", "label": "B"}],
            "edges": [{"from": "1", "to": "2"}],
        }
    }
    monkeypatch.setattr(
        "app.mcp.drawio.call_drawio_mcp_open_mermaid",
        lambda mermaid: {
            "status": "ok",
            "edit_url": "https://app.diagrams.net/?from=mcp#create=x",
            "tool_name": "open_drawio_mermaid",
            "tools": ["open_drawio_mermaid"],
            "source": "mcp_stdio",
        },
    )
    monkeypatch.setattr(
        "app.mcp.drawio.render_mermaid_png",
        lambda m: {"png_url": None, "png_data_url": None, "error": "skip"},
    )
    result = run_drawio_mcp_for_visual(structured=structured, goal="Flow")
    assert result["status"] == "ok"
    assert result["source"] == "mcp_stdio"
    assert result["mcp_tool"] == "open_drawio_mermaid"
    assert "from=mcp" in result["edit_url"]


def test_call_drawio_mcp_respects_spawn_flag(monkeypatch):
    monkeypatch.setattr("app.mcp.drawio._mcp_process_enabled", lambda: False)
    out = call_drawio_mcp_open_mermaid("flowchart TD\n  a-->b")
    assert out["status"] == "skipped"
    assert out["error"] == "mcp_spawn_disabled"


class _FakeClient:
    """Mimics McpStdioClient's real surface (start/close, not just __enter__)."""

    instances_started = 0

    def __init__(self, *a, **k):
        self.closed = False

    def start(self):
        _FakeClient.instances_started += 1

    def close(self):
        self.closed = True

    def initialize(self, **k):
        return {"serverInfo": {"name": "@drawio/mcp", "version": "1.5.0"}}

    def list_tools(self):
        return [{"name": "open_drawio_mermaid"}]

    def call_tool(self, name, arguments, timeout=None):
        assert name == "open_drawio_mermaid"
        assert "content" in arguments
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Draw.io Editor URL:\n"
                        f"https://app.diagrams.net/?grid=0#create={arguments['content'][:6]}\n\n"
                        "Opened."
                    ),
                }
            ]
        }


def test_call_drawio_mcp_open_mermaid_success(monkeypatch):
    """Simulate a successful stdio MCP session without spawning npx."""
    _FakeClient.instances_started = 0
    monkeypatch.setattr("app.mcp.drawio._mcp_process_enabled", lambda: True)
    monkeypatch.setattr("app.mcp.drawio.McpStdioClient", _FakeClient)
    out = call_drawio_mcp_open_mermaid("flowchart TD\n  a-->b")
    assert out["status"] == "ok"
    assert out["source"] == "mcp_stdio"
    assert "create=" in out["edit_url"]
    assert out["tool_name"] == "open_drawio_mermaid"
    assert _FakeClient.instances_started == 1


def test_render_section_diagrams_reuses_one_session(monkeypatch):
    """N sections must spawn exactly one MCP process, not one per section."""
    _FakeClient.instances_started = 0
    monkeypatch.setattr("app.mcp.drawio._mcp_process_enabled", lambda: True)
    monkeypatch.setattr("app.mcp.drawio.McpStdioClient", _FakeClient)

    from app.mcp.drawio import render_section_diagrams_via_mcp

    sections = {
        1: ("flowchart TD\n  a-->b", "flowchart"),
        2: ("flowchart TD\n  x-->y", "tree"),
        3: ("sequenceDiagram\n  A->>B: hi", "sequence"),
    }
    results = render_section_diagrams_via_mcp(sections)
    assert set(results.keys()) == {1, 2, 3}
    for idx, res in results.items():
        assert res["status"] == "ok"
        assert res["source"] == "mcp_stdio"
        assert res["diagram_kind"] == sections[idx][1]
        assert res["mermaid"] == sections[idx][0]
    # Exactly one process spawned across all three sections.
    assert _FakeClient.instances_started == 1


def test_render_section_diagrams_falls_back_when_spawn_disabled(monkeypatch):
    monkeypatch.setattr("app.mcp.drawio._mcp_process_enabled", lambda: False)

    from app.mcp.drawio import render_section_diagrams_via_mcp

    sections = {1: ("flowchart TD\n  a-->b", "flowchart")}
    results = render_section_diagrams_via_mcp(sections)
    assert results[1]["status"] == "ok"
    assert results[1]["source"] == "local_fallback"
    assert "app.diagrams.net" in results[1]["edit_url"]


def test_parse_tool_text_and_urls():
    text = parse_tool_text_content(
        {
            "content": [
                {
                    "type": "text",
                    "text": "Draw.io Editor URL:\nhttps://app.diagrams.net/?x=1#create=abc\n\nOpened.",
                }
            ]
        }
    )
    urls = extract_urls(text)
    assert urls and urls[0].startswith("https://app.diagrams.net/")


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
