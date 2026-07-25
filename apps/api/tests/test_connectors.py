"""Agent connector catalog for the Agents page."""

from app.agents.connectors import connectors_overview, list_connectors
from app.config import settings


def test_list_connectors_includes_builtins_and_drawio():
    items = list_connectors()
    ids = {c["id"] for c in items}
    assert "docs_search" in ids
    assert "web_search" in ids
    assert "create_note" in ids
    assert "visual_summary" in ids
    assert "mcp_drawio" in ids


def test_create_note_requires_approval():
    note = next(c for c in list_connectors() if c["id"] == "create_note")
    assert note["requires_approval"] is True
    assert note["status"] == "available"


def test_drawio_coming_soon_by_default(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    monkeypatch.setattr(settings, "mcp_drawio_enabled", False)
    drawio = next(c for c in list_connectors() if c["id"] == "mcp_drawio")
    assert drawio["kind"] == "mcp"
    assert drawio["status"] == "coming_soon"
    assert "npx" in (drawio.get("install_hint") or "")


def test_drawio_configured_when_flags_on(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_drawio_enabled", True)
    drawio = next(c for c in list_connectors() if c["id"] == "mcp_drawio")
    assert drawio["status"] == "configured"


def test_overview_counts():
    overview = connectors_overview()
    assert overview["counts"]["total"] == len(overview["connectors"])
    assert overview["counts"]["total"] >= 8
