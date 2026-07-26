"""draw.io connector for the Visual Summary phase.

When the user enables ``mcp_drawio`` on the Agents page, the visual pipeline
calls this module after ``render_ui`` to:

1. Build Mermaid from structured process_flow / interaction_sequence / steps
2. Prefer a **real MCP stdio session** to ``npx -y @drawio/mcp`` and call
   ``open_drawio_mermaid`` (official draw.io MCP tool)
3. Fall back to a local diagrams.net create-URL + mermaid.ink PNG if the MCP
   process is unavailable (no Node, npx timeout, cloud sandbox, etc.)

The main research agent does not call draw.io mid-run — this is a visual-phase
export path, matching the connector catalog phase=visual.
"""

from __future__ import annotations

import base64
import logging
import re
import urllib.parse
from typing import Any

import httpx

from app.mcp.stdio_client import (
    McpStdioClient,
    McpStdioError,
    extract_urls,
    parse_tool_text_content,
)

logger = logging.getLogger(__name__)

# Cap embedded PNG size so presentation_spec stays free-tier friendly.
_MAX_PNG_BYTES = 1_500_000


def _sanitize_id(label: str, used: set[str]) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]", "_", (label or "n").strip()) or "n"
    if raw[0].isdigit():
        raw = f"n_{raw}"
    base = raw[:40]
    candidate = base
    i = 2
    while candidate in used:
        candidate = f"{base}_{i}"
        i += 1
    used.add(candidate)
    return candidate


def _escape_mermaid_label(text: str) -> str:
    t = (text or "").replace('"', "'").replace("\n", " ").strip()
    return t[:80] or "step"


def mermaid_from_structured(structured: dict[str, Any] | None) -> tuple[str | None, str]:
    """Return (mermaid_source, diagram_kind) from structured handoff content."""
    if not isinstance(structured, dict):
        return None, "none"

    flow = structured.get("process_flow")
    if isinstance(flow, dict):
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        if isinstance(nodes, list) and len(nodes) >= 2:
            used: set[str] = set()
            id_map: dict[str, str] = {}
            lines = ["flowchart TD"]
            for n in nodes:
                if not isinstance(n, dict):
                    continue
                raw_id = str(n.get("id") or n.get("label") or "n")
                nid = _sanitize_id(raw_id, used)
                id_map[str(n.get("id") or raw_id)] = nid
                label = _escape_mermaid_label(str(n.get("label") or n.get("id") or nid))
                lines.append(f'  {nid}["{label}"]')
            for e in edges if isinstance(edges, list) else []:
                if not isinstance(e, dict):
                    continue
                src = id_map.get(str(e.get("from") or e.get("source") or ""))
                dst = id_map.get(str(e.get("to") or e.get("target") or ""))
                if not src or not dst:
                    continue
                elabel = e.get("label")
                if elabel:
                    lines.append(
                        f'  {src} -->|{_escape_mermaid_label(str(elabel))}| {dst}'
                    )
                else:
                    lines.append(f"  {src} --> {dst}")
            if len(lines) > 1:
                return "\n".join(lines), "flowchart"

    seq = structured.get("interaction_sequence")
    if isinstance(seq, dict):
        messages = seq.get("messages") or seq.get("steps") or []
        actors = seq.get("actors") or []
        if isinstance(messages, list) and messages:
            lines = ["sequenceDiagram"]
            seen_actors: set[str] = set()
            for a in actors if isinstance(actors, list) else []:
                name = str(a.get("name") if isinstance(a, dict) else a).strip()
                if name and name not in seen_actors:
                    seen_actors.add(name)
                    safe = re.sub(r"[^A-Za-z0-9_]", "_", name)[:30] or "A"
                    lines.append(f"  participant {safe} as {name[:40]}")
            for m in messages:
                if not isinstance(m, dict):
                    continue
                fr = str(m.get("from") or m.get("sender") or "A").strip()
                to = str(m.get("to") or m.get("receiver") or "B").strip()
                msg = _escape_mermaid_label(str(m.get("message") or m.get("label") or ""))
                fr_s = re.sub(r"[^A-Za-z0-9_]", "_", fr)[:30] or "A"
                to_s = re.sub(r"[^A-Za-z0-9_]", "_", to)[:30] or "B"
                lines.append(f"  {fr_s}->>{to_s}: {msg}")
            if len(lines) > 1:
                return "\n".join(lines), "sequence"

    # Fallback: ordered actions as a simple flowchart
    actions = structured.get("ordered_actions") or structured.get("steps") or []
    if isinstance(actions, list) and len(actions) >= 2:
        used = set()
        lines = ["flowchart TD"]
        prev = None
        for i, step in enumerate(actions[:12]):
            if isinstance(step, dict):
                label = str(
                    step.get("title")
                    or step.get("text")
                    or step.get("label")
                    or f"Step {i + 1}"
                )
            else:
                label = str(step)
            nid = _sanitize_id(f"s{i}", used)
            lines.append(f'  {nid}["{_escape_mermaid_label(label)}"]')
            if prev:
                lines.append(f"  {prev} --> {nid}")
            prev = nid
        return "\n".join(lines), "flowchart"

    # Fallback: key_points / sections as linear flow
    points = structured.get("key_points") or []
    if isinstance(points, list) and len(points) >= 2:
        used = set()
        lines = ["flowchart TD"]
        prev = None
        for i, pt in enumerate(points[:10]):
            if isinstance(pt, dict):
                label = str(pt.get("text") or pt.get("title") or pt.get("label") or f"Point {i + 1}")
            else:
                label = str(pt)
            nid = _sanitize_id(f"k{i}", used)
            lines.append(f'  {nid}["{_escape_mermaid_label(label)}"]')
            if prev:
                lines.append(f"  {prev} --> {nid}")
            prev = nid
        return "\n".join(lines), "flowchart"

    sections = structured.get("sections") or []
    if isinstance(sections, list) and len(sections) >= 2:
        used = set()
        lines = ["flowchart TD"]
        prev = None
        for i, sec in enumerate(sections[:10]):
            if isinstance(sec, dict):
                label = str(sec.get("title") or sec.get("heading") or f"Section {i + 1}")
            else:
                label = str(sec)
            nid = _sanitize_id(f"sec{i}", used)
            lines.append(f'  {nid}["{_escape_mermaid_label(label)}"]')
            if prev:
                lines.append(f"  {prev} --> {nid}")
            prev = nid
        return "\n".join(lines), "flowchart"

    return None, "none"


def mermaid_from_presentation_spec(
    spec: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """Build Mermaid from rendered generative UI diagram blocks."""
    if not isinstance(spec, dict):
        return None, "none"
    blocks = spec.get("blocks") or []
    if not isinstance(blocks, list):
        return None, "none"

    for b in blocks:
        if not isinstance(b, dict):
            continue
        btype = str(b.get("type") or "")
        if btype == "flow_diagram":
            nodes = b.get("nodes") or []
            edges = b.get("edges") or []
            if isinstance(nodes, list) and len(nodes) >= 2:
                return mermaid_from_structured(
                    {"process_flow": {"nodes": nodes, "edges": edges}}
                )
        if btype == "sequence_diagram":
            actors = b.get("actors") or []
            messages = b.get("messages") or []
            if isinstance(messages, list) and messages:
                return mermaid_from_structured(
                    {
                        "interaction_sequence": {
                            "actors": actors,
                            "messages": messages,
                        }
                    }
                )
        if btype == "steps":
            items = b.get("items") or []
            if isinstance(items, list) and len(items) >= 2:
                return mermaid_from_structured({"ordered_actions": items})

    return None, "none"


def drawio_edit_url(mermaid: str, *, title: str = "Sourcebook diagram") -> str:
    """Build a diagrams.net URL that opens with Mermaid create payload (fallback)."""
    # Lightweight fallback when the MCP process is not available. The official
    # MCP server uses pako deflateRaw + #create= JSON; this simpler path still
    # opens Mermaid in draw.io for most diagrams.
    encoded = urllib.parse.quote(mermaid, safe="")
    title_q = urllib.parse.quote(title[:80] or "Sourcebook diagram")
    base = _drawio_base_url()
    return (
        f"{base}"
        f"?splash=0&libs=general&title={title_q}"
        f"#create=data:text/plain,{encoded}"
    )


def _drawio_base_url() -> str:
    try:
        from app.config import settings

        base = (getattr(settings, "drawio_base_url", None) or "").strip()
        if base:
            return base if base.endswith("/") else f"{base}/"
    except Exception:
        pass
    return "https://app.diagrams.net/"


def _mcp_command() -> list[str]:
    """Resolve argv for the draw.io MCP stdio server from settings."""
    try:
        from app.config import settings

        cmd = (settings.mcp_drawio_command or "npx").strip() or "npx"
        raw_args = (settings.mcp_drawio_args or "-y,@drawio/mcp").strip()
        args = [a.strip() for a in raw_args.split(",") if a.strip()]
        if not args:
            args = ["-y", "@drawio/mcp"]
        return [cmd, *args]
    except Exception:
        return ["npx", "-y", "@drawio/mcp"]


def _mcp_timeout() -> float:
    try:
        from app.config import settings

        return float(getattr(settings, "mcp_drawio_timeout_seconds", 45) or 45)
    except Exception:
        return 45.0


def _mcp_process_enabled() -> bool:
    """Whether to spawn the real @drawio/mcp process (can be disabled in CI)."""
    try:
        from app.config import settings

        return bool(getattr(settings, "mcp_drawio_spawn", True))
    except Exception:
        return True


def open_drawio_mcp_session() -> tuple[McpStdioClient | None, dict[str, Any]]:
    """
    Spawn ``@drawio/mcp`` over stdio, initialize, and list tools once.

    Returns (client, meta). ``client`` is ``None`` (already closed) when spawn
    is disabled or the handshake fails — callers should fall back to local URL
    generation for every section in that case. Does not raise.
    """
    if not _mcp_process_enabled():
        return None, {"status": "skipped", "error": "mcp_spawn_disabled"}

    command = _mcp_command()
    timeout = _mcp_timeout()
    env = {
        "DRAWIO_BASE_URL": _drawio_base_url(),
        # On headless servers browser open is pointless; MCP still returns URL.
        "BROWSER": "echo",
        "DISPLAY": "",
    }
    client = McpStdioClient(command, timeout=timeout, env=env)
    try:
        client.start()
        init = client.initialize(client_name="sourcebook", client_version="0.1.0")
        tools = client.list_tools()
        tool_names = [str(t.get("name") or "") for t in tools]
        return client, {
            "status": "ok",
            "tools": tool_names,
            "server": (init or {}).get("serverInfo"),
        }
    except McpStdioError as e:
        logger.warning("draw.io MCP stdio failed: %s", e)
        client.close()
        return None, {"status": "error", "error": str(e)[:500], "source": "mcp_stdio"}
    except Exception as e:
        logger.exception("draw.io MCP unexpected failure")
        client.close()
        return None, {
            "status": "error",
            "error": f"{type(e).__name__}: {e}"[:500],
            "source": "mcp_stdio",
        }


def call_open_mermaid(
    client: McpStdioClient,
    mermaid: str,
    *,
    tool_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Call ``open_drawio_mermaid`` (or a fuzzy-matched fork name) on an already
    -initialized session. Does not raise — errors come back as a status dict.
    """
    if not mermaid.strip():
        return {"status": "error", "error": "empty_mermaid"}

    tool_names = tool_names if tool_names is not None else []
    preferred = "open_drawio_mermaid"
    if tool_names and preferred not in tool_names:
        # Some forks may rename tools — try a fuzzy match.
        for n in tool_names:
            if "mermaid" in n.lower() and "open" in n.lower():
                preferred = n
                break
        else:
            return {
                "status": "error",
                "error": "open_drawio_mermaid_not_found",
                "tools": tool_names,
            }
    try:
        result = client.call_tool(
            preferred,
            {"content": mermaid, "lightbox": False, "dark": "auto"},
            timeout=_mcp_timeout(),
        )
        text = parse_tool_text_content(result)
        urls = extract_urls(text)
        is_error = bool(result.get("isError"))
        if is_error:
            return {
                "status": "error",
                "error": text[:400] or "tool_isError",
                "tools": tool_names,
                "tool_text": text[:800],
            }
        edit_url = urls[0] if urls else None
        if not edit_url:
            return {
                "status": "error",
                "error": "no_url_in_mcp_response",
                "tool_text": text[:800],
                "tools": tool_names,
            }
        return {
            "status": "ok",
            "edit_url": edit_url,
            "tool_text": text[:800],
            "tools": tool_names,
            "tool_name": preferred,
            "source": "mcp_stdio",
        }
    except McpStdioError as e:
        logger.warning("draw.io MCP stdio call failed: %s", e)
        return {"status": "error", "error": str(e)[:500], "source": "mcp_stdio"}
    except Exception as e:
        logger.exception("draw.io MCP unexpected call failure")
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}"[:500],
            "source": "mcp_stdio",
        }


def call_drawio_mcp_open_mermaid(mermaid: str) -> dict[str, Any]:
    """
    Spawn ``@drawio/mcp`` over stdio and call ``open_drawio_mermaid`` once.

    Thin wrapper around :func:`open_drawio_mcp_session` +
    :func:`call_open_mermaid` for the single-diagram (non study-sheet) path.
    Returns a dict with status, edit_url (if any), tool_text, tools, error.
    Does not raise — callers fall back to local URL generation.
    """
    client, meta = open_drawio_mcp_session()
    if client is None:
        return meta
    try:
        result = call_open_mermaid(client, mermaid, tool_names=meta.get("tools"))
        if result.get("status") == "ok":
            result["server"] = meta.get("server")
        return result
    finally:
        client.close()


def render_section_diagrams_via_mcp(
    sections_mermaid: dict[int, tuple[str, str]],
) -> dict[int, dict[str, Any]]:
    """
    Render one diagram per study-sheet section, reusing a single MCP session.

    ``sections_mermaid`` maps 1-based section_index -> (mermaid, diagram_kind).
    Sections are rendered **one by one** against the same stdio session (one
    ``npx @drawio/mcp`` spawn total, not one per section). Returns
    section_index -> result dict (same shape as ``call_drawio_mcp_open_mermaid``,
    plus ``diagram_kind``). Never raises — MCP failures fall back to a local
    diagrams.net edit URL per section.
    """
    out: dict[int, dict[str, Any]] = {}
    if not sections_mermaid:
        return out

    client, meta = open_drawio_mcp_session()
    tool_names = meta.get("tools") if isinstance(meta.get("tools"), list) else []
    try:
        for section_index, (mermaid, diagram_kind) in sections_mermaid.items():
            if client is not None:
                result = call_open_mermaid(client, mermaid, tool_names=tool_names)
            else:
                result = {"status": "error", "error": meta.get("error") or "mcp_unavailable"}
            if result.get("status") != "ok" or not result.get("edit_url"):
                result = {
                    "status": "ok",
                    "edit_url": drawio_edit_url(mermaid, title=f"Section {section_index}"),
                    "source": "local_fallback",
                    "tool_name": None,
                    "mcp_error": result.get("error"),
                }
            result["diagram_kind"] = diagram_kind
            result["mermaid"] = mermaid
            png = render_mermaid_png(mermaid)
            result["png_url"] = png.get("png_url")
            result["png_data_url"] = png.get("png_data_url")
            result["preview_url"] = png.get("png_data_url") or png.get("png_url")
            result["png_error"] = png.get("error")
            out[section_index] = result
    finally:
        if client is not None:
            client.close()
    return out


def mermaid_encode(mermaid: str) -> str:
    """URL-safe base64 used by mermaid.ink / Kroki-style renderers."""
    return base64.urlsafe_b64encode(mermaid.encode("utf-8")).decode("ascii").rstrip("=")


def mermaid_png_urls(mermaid: str) -> list[str]:
    """Candidate PNG render URLs (tried in order)."""
    enc = mermaid_encode(mermaid)
    return [
        f"https://mermaid.ink/img/{enc}?type=png",
        f"https://mermaid.ink/img/{enc}",
        f"https://kroki.io/mermaid/png/{enc}",
    ]


def render_mermaid_png(mermaid: str) -> dict[str, Any]:
    """
    Render Mermaid to PNG for the Visual Summary tab.

    Returns keys: png_url, png_data_url (optional embedded data URI), error.
    """
    urls = mermaid_png_urls(mermaid)
    last_error: str | None = None
    for url in urls:
        try:
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=8.0), follow_redirects=True) as client:
                resp = client.get(url)
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code} from renderer"
                continue
            content_type = (resp.headers.get("content-type") or "").lower()
            body = resp.content or b""
            if not body:
                last_error = "empty PNG body"
                continue
            # mermaid.ink may return SVG for some paths — only accept image payloads.
            if "svg" in content_type and body[:200].lstrip().startswith(b"<"):
                last_error = "renderer returned SVG, not PNG"
                continue
            if len(body) > _MAX_PNG_BYTES:
                # Still usable as remote URL without embedding.
                return {
                    "png_url": url,
                    "png_data_url": None,
                    "png_bytes": len(body),
                    "embedded": False,
                }
            b64 = base64.b64encode(body).decode("ascii")
            return {
                "png_url": url,
                "png_data_url": f"data:image/png;base64,{b64}",
                "png_bytes": len(body),
                "embedded": True,
            }
        except Exception as e:  # network / TLS / timeout
            last_error = f"{type(e).__name__}: {e}"
            continue
    return {
        "png_url": urls[0] if urls else None,
        "png_data_url": None,
        "error": last_error or "png_render_failed",
        "embedded": False,
    }


def run_drawio_mcp_for_visual(
    *,
    structured: dict[str, Any] | None,
    goal: str = "",
    presentation_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Produce draw.io connector output for the visual summary.

    1. Build Mermaid from structured handoff / rendered UI / goal fallback
    2. Call real ``@drawio/mcp`` via stdio when spawn is enabled
    3. Always render a PNG preview (mermaid.ink) for the Visual tab
    4. Soft-fail with skipped/error details — never raise into the visual pipeline
    """
    mermaid, kind = mermaid_from_structured(structured)
    if not mermaid:
        mermaid, kind = mermaid_from_presentation_spec(presentation_spec)
    if not mermaid and (goal or "").strip():
        # Last resort so enabled MCP still produces an editable diagram shell.
        g = _escape_mermaid_label((goal or "").strip()[:70])
        mermaid = (
            "flowchart TD\n"
            f'  start["Start"] --> topic["{g}"]\n'
            '  topic --> visual["Visual summary"]\n'
            '  visual --> done["Done"]'
        )
        kind = "flowchart"

    if not mermaid:
        return {
            "status": "skipped",
            "reason": "no_diagram_structure",
            "detail": (
                "No process_flow, sequence, steps, or rendered diagram blocks "
                "to send to draw.io."
            ),
            "provider": "draw.io",
            "connector_id": "mcp_drawio",
        }

    title = (goal or "Sourcebook diagram").strip()[:80] or "Sourcebook diagram"
    mcp_meta = call_drawio_mcp_open_mermaid(mermaid)
    if mcp_meta.get("status") == "ok" and mcp_meta.get("edit_url"):
        edit_url = str(mcp_meta["edit_url"])
        source = "mcp_stdio"
        mcp_tool = mcp_meta.get("tool_name") or "open_drawio_mermaid"
        mcp_error = None
    else:
        edit_url = drawio_edit_url(mermaid, title=title)
        source = "local_fallback"
        mcp_tool = None
        mcp_error = mcp_meta.get("error")

    png = render_mermaid_png(mermaid)
    # Prefer embedded data URI for reliable display in the Visual Summary tab.
    preview_url = png.get("png_data_url") or png.get("png_url")

    return {
        "status": "ok",
        "provider": "draw.io",
        "connector_id": "mcp_drawio",
        "diagram_kind": kind,
        "mermaid": mermaid,
        "edit_url": edit_url,
        "preview_url": preview_url,
        "png_url": png.get("png_url"),
        "png_data_url": png.get("png_data_url"),
        "png_bytes": png.get("png_bytes"),
        "png_error": png.get("error"),
        "source": source,
        "mcp_tool": mcp_tool,
        "mcp_error": mcp_error,
        "mcp_tools": mcp_meta.get("tools"),
        "mcp_server": mcp_meta.get("server"),
    }


def attach_drawio_to_spec(spec: dict[str, Any], drawio_result: dict[str, Any]) -> dict[str, Any]:
    """Merge draw.io MCP result into presentation_spec.meta (+ optional image block)."""
    out = dict(spec)
    meta = dict(out.get("meta") or {}) if isinstance(out.get("meta"), dict) else {}
    if drawio_result.get("status") == "ok":
        image_src = (
            drawio_result.get("png_data_url")
            or drawio_result.get("preview_url")
            or drawio_result.get("png_url")
        )
        meta["drawio"] = {
            "mermaid": drawio_result.get("mermaid"),
            "edit_url": drawio_result.get("edit_url"),
            "preview_url": image_src,
            "png_url": drawio_result.get("png_url"),
            "png_data_url": drawio_result.get("png_data_url"),
            "diagram_kind": drawio_result.get("diagram_kind"),
            "connector_id": "mcp_drawio",
            "png_error": drawio_result.get("png_error"),
            "source": drawio_result.get("source"),
            "mcp_tool": drawio_result.get("mcp_tool"),
            "mcp_error": drawio_result.get("mcp_error"),
        }
        # Also inject a full-width image-like callout via summary body is not ideal;
        # the Visual Summary UI reads meta.drawio for the diagram panel.
    elif drawio_result.get("status") == "skipped":
        meta["drawio"] = {
            "status": "skipped",
            "reason": drawio_result.get("reason"),
            "detail": drawio_result.get("detail"),
        }
    out["meta"] = meta
    return out


def enabled_mcp_ids_from_run(run: Any) -> list[str]:
    opts = getattr(run, "run_options", None) or {}
    if not isinstance(opts, dict):
        return []
    raw = opts.get("enabled_mcp_ids") or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]
