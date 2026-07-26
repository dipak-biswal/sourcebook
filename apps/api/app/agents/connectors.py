"""Agent connector catalog for the Agents page UI.

Built-in tools power the agent loop. MCP connectors (e.g. draw.io) are listed
separately so the UI can show MCP-only toggles next to Run agent.
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
        "enabled_by_default": True,
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
        "enabled_by_default": True,
        "phase": "visual",
        "tool_names": tool_names,
        "requires_approval": False,
        "icon": icon,
        "provider": "sourcebook",
    }


def _mcp_drawio() -> dict[str, Any]:
    """draw.io MCP — real stdio server via `npx @drawio/mcp`.

    Always listed as *available* (no paid plan). Server flags only set whether
    it is on by default for this deploy (`enabled_by_default`).

    When the user enables this connector on a run, Visual Summary spawns the
    official MCP process and calls ``open_drawio_mermaid`` (falls back to a
    local diagrams.net URL if Node/npx is unavailable).
    """
    server_on = bool(settings.mcp_enabled and settings.mcp_drawio_enabled)
    spawn_on = bool(getattr(settings, "mcp_drawio_spawn", True))
    return {
        "id": "mcp_drawio",
        "name": "draw.io",
        "description": (
            "When on, Visual Summary runs the official draw.io MCP server "
            "(`npx -y @drawio/mcp`) and calls open_drawio_mermaid after layout/"
            "render. Falls back to a local edit URL if the process is unavailable."
        ),
        "kind": "mcp",
        "status": "available",
        "enabled_by_default": server_on,
        "phase": "visual",
        "tool_names": ["mcp_drawio", "open_drawio_mermaid"],
        "requires_approval": False,
        "icon": "diagram",
        "provider": "draw.io",
        "install_hint": "npx -y @drawio/mcp  (requires Node.js 18+)",
        "docs_url": "https://www.drawio.com/docs/manual/generate/drawio-mcp-server/",
        "runtime": {
            "spawn": spawn_on,
            "command": getattr(settings, "mcp_drawio_command", "npx"),
            "args": getattr(settings, "mcp_drawio_args", "-y,@drawio/mcp"),
        },
    }


def list_connectors() -> list[dict[str, Any]]:
    """Full catalog (built-ins + pipeline + MCP)."""
    return [
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


def list_mcp_connectors() -> list[dict[str, Any]]:
    """MCP-only connectors for the Agents page dropdown."""
    return [c for c in list_connectors() if c["kind"] == "mcp"]


def connectors_overview() -> dict[str, Any]:
    items = list_connectors()
    mcp_items = [c for c in items if c["kind"] == "mcp"]
    counts = {
        "total": len(items),
        "available": sum(1 for c in items if c["status"] == "available"),
        "configured": sum(1 for c in items if c["status"] == "configured"),
        "coming_soon": sum(1 for c in items if c["status"] == "coming_soon"),
        "disabled": sum(1 for c in items if c["status"] == "disabled"),
        "mcp": len(mcp_items),
        "builtin": sum(1 for c in items if c["kind"] == "builtin"),
    }
    return {
        "mcp_enabled": bool(settings.mcp_enabled),
        "connectors": items,
        "mcp_connectors": mcp_items,
        "counts": counts,
    }
