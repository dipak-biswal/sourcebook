"""Agent connector catalog for the Agents page UI.

Built-in tools ship with Sourcebook. MCP connectors (e.g. draw.io) are listed
here so the UI can show what is available, configured, or coming soon — even
before the MCP runtime is fully wired into the agent loop.
"""

from __future__ import annotations

from typing import Any, Literal

from app.config import settings

ConnectorKind = Literal["builtin", "mcp", "pipeline"]
ConnectorStatus = Literal["available", "configured", "coming_soon", "disabled"]
ConnectorPhase = Literal["main", "visual", "both"]


def _builtin(
    *,
    id: str,
    name: str,
    description: str,
    phase: ConnectorPhase,
    tool_names: list[str],
    requires_approval: bool = False,
    icon: str = "tool",
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "description": description,
        "kind": "builtin",
        "status": "available",
        "phase": phase,
        "tool_names": tool_names,
        "requires_approval": requires_approval,
        "icon": icon,
        "provider": "sourcebook",
    }


def _pipeline(
    *,
    id: str,
    name: str,
    description: str,
    tool_names: list[str],
    icon: str = "layout",
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "description": description,
        "kind": "pipeline",
        "status": "available",
        "phase": "visual",
        "tool_names": tool_names,
        "requires_approval": False,
        "icon": icon,
        "provider": "sourcebook",
    }


def _mcp_drawio() -> dict[str, Any]:
    """draw.io MCP — free local server via `npx @drawio/mcp`."""
    enabled = bool(settings.mcp_enabled and settings.mcp_drawio_enabled)
    # Runtime call path lands in a later PR; "configured" means env is ready.
    if enabled:
        status: ConnectorStatus = "configured"
        description = (
            "Generate diagrams via draw.io MCP (`npx @drawio/mcp`). "
            "Configured — wiring into the visual agent is enabled for this deploy."
        )
    else:
        status = "coming_soon"
        description = (
            "Generate and open diagrams with draw.io (Mermaid, CSV, .drawio). "
            "Free local MCP: npx @drawio/mcp. Enable with MCP_ENABLED and "
            "MCP_DRAWIO_ENABLED when ready."
        )
    return {
        "id": "mcp_drawio",
        "name": "draw.io",
        "description": description,
        "kind": "mcp",
        "status": status,
        "phase": "visual",
        "tool_names": ["mcp_drawio"],
        "requires_approval": False,
        "icon": "diagram",
        "provider": "draw.io",
        "install_hint": "npx -y @drawio/mcp",
        "docs_url": "https://www.drawio.com/docs/manual/generate/drawio-mcp-server/",
    }


def list_connectors() -> list[dict[str, Any]]:
    """All connectors the Agents UI should surface (order = display order)."""
    connectors: list[dict[str, Any]] = [
        _builtin(
            id="docs_list",
            name="List documents",
            description="List files in the current workspace and their ingest status.",
            phase="main",
            tool_names=["list_documents"],
            icon="files",
        ),
        _builtin(
            id="docs_search",
            name="Search documents",
            description="Semantic search over ingested document chunks in the workspace.",
            phase="main",
            tool_names=["search_documents"],
            icon="search",
        ),
        _builtin(
            id="docs_read",
            name="Read document",
            description="Read full text from a document, with pagination across chunks.",
            phase="main",
            tool_names=["read_document"],
            icon="file",
        ),
        _builtin(
            id="web_search",
            name="Web search",
            description=(
                "Search the public web when workspace policy allows external context."
            ),
            phase="main",
            tool_names=["web_search"],
            icon="globe",
        ),
        _builtin(
            id="fetch_url",
            name="Fetch URL",
            description="Fetch and read a web page found via search or provided in the goal.",
            phase="main",
            tool_names=["fetch_url"],
            icon="link",
        ),
        _builtin(
            id="create_note",
            name="Create note",
            description="Draft a workspace note. Requires your approval before it saves.",
            phase="main",
            tool_names=["create_note"],
            requires_approval=True,
            icon="note",
        ),
        _builtin(
            id="current_date",
            name="Current date",
            description="Resolve today's date (UTC) for time-sensitive searches and labels.",
            phase="both",
            tool_names=["get_current_date"],
            icon="calendar",
        ),
        _pipeline(
            id="visual_summary",
            name="Visual summary",
            description=(
                "After the main agent answers, plan layout and render generative UI "
                "(flow diagrams, tables, FAQ, and more)."
            ),
            tool_names=["plan_layout", "render_ui"],
            icon="layout",
        ),
        _mcp_drawio(),
    ]
    return connectors


def connectors_overview() -> dict[str, Any]:
    items = list_connectors()
    counts = {
        "total": len(items),
        "available": sum(1 for c in items if c["status"] == "available"),
        "configured": sum(1 for c in items if c["status"] == "configured"),
        "coming_soon": sum(1 for c in items if c["status"] == "coming_soon"),
        "disabled": sum(1 for c in items if c["status"] == "disabled"),
        "mcp": sum(1 for c in items if c["kind"] == "mcp"),
        "builtin": sum(1 for c in items if c["kind"] == "builtin"),
    }
    return {
        "mcp_enabled": bool(settings.mcp_enabled),
        "connectors": items,
        "counts": counts,
    }
