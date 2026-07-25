"""draw.io export connector for the Visual Summary phase.

When the user enables ``mcp_drawio`` on the Agents page, the visual pipeline
calls this module after ``render_ui`` to:

1. Build Mermaid from structured process_flow / interaction_sequence
2. Produce a diagrams.net edit URL

Despite the connector id, this does not speak the Model Context Protocol —
it is plain code that builds a Mermaid diagram and links out to
diagrams.net/mermaid.ink. The agent still uses Sourcebook's generative UI
blocks; draw.io is an extra export/edit path when the toggle is on.
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Any

import httpx

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
    """Build a diagrams.net URL that opens with Mermaid create payload."""
    # data URL + create= is what many draw.io MCP open_* tools effectively use.
    encoded = urllib.parse.quote(mermaid, safe="")
    title_q = urllib.parse.quote(title[:80] or "Sourcebook diagram")
    return (
        "https://app.diagrams.net/"
        f"?splash=0&libs=general&title={title_q}"
        f"#create=data:text/plain,{encoded}"
    )


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

    Prefer structured handoff → rendered UI blocks → goal fallback.
    Always returns a tool-result shaped dict (success or soft skip).
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
    edit_url = drawio_edit_url(mermaid, title=title)
    png = render_mermaid_png(mermaid)
    # Prefer embedded data URI for reliable display in the Visual Summary tab.
    preview_url = png.get("png_data_url") or png.get("png_url")

    result: dict[str, Any] = {
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
        "source": "sourcebook_drawio_mcp",
    }
    return result


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
