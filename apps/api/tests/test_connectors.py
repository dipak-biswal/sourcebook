"""Agent connector catalog for the Agents page."""

from app.agents.connectors import connectors_overview, list_connectors, list_mcp_connectors
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


def test_drawio_available_mcp_not_coming_soon(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    monkeypatch.setattr(settings, "mcp_drawio_enabled", False)
    drawio = next(c for c in list_connectors() if c["id"] == "mcp_drawio")
    assert drawio["kind"] == "mcp"
    assert drawio["status"] == "available"
    assert drawio["enabled_by_default"] is False
    assert "npx" in (drawio.get("install_hint") or "")


def test_drawio_enabled_by_default_when_flags_on(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_drawio_enabled", True)
    drawio = next(c for c in list_connectors() if c["id"] == "mcp_drawio")
    assert drawio["status"] == "available"
    assert drawio["enabled_by_default"] is True


def test_mcp_connectors_only():
    mcp = list_mcp_connectors()
    assert mcp
    assert all(c["kind"] == "mcp" for c in mcp)


def test_overview_includes_mcp_connectors():
    overview = connectors_overview()
    assert overview["counts"]["total"] == len(overview["connectors"])
    assert overview["mcp_connectors"] == [
        c for c in overview["connectors"] if c["kind"] == "mcp"
    ]
