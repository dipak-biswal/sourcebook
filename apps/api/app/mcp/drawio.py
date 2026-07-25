"""draw.io MCP connector for the Visual Summary phase.

When the user enables ``mcp_drawio`` on the Agents page, the visual pipeline
calls this module after ``render_ui`` to:

1. Build Mermaid from structured process_flow / interaction_sequence
2. Produce a diagrams.net edit URL (MCP-compatible handoff)
3. Optionally try the local ``npx @drawio/mcp`` tool server (best-effort)

The agent still uses Sourcebook's generative UI blocks; draw.io is an extra
export/edit path when the MCP toggle is on.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import urllib.parse
from typing import Any


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
                label = str(step.get("title") or step.get("text") or step.get("label") or f"Step {i+1}")
            else:
                label = str(step)
            nid = _sanitize_id(f"s{i}", used)
            lines.append(f'  {nid}["{_escape_mermaid_label(label)}"]')
            if prev:
                lines.append(f"  {prev} --> {nid}")
            prev = nid
        return "\n".join(lines), "flowchart"

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


def _try_npx_drawio_mcp(mermaid: str) -> dict[str, Any] | None:
    """Best-effort: confirm npx/@drawio/mcp is available (does not block UI)."""
    if not shutil.which("npx"):
        return None
    try:
        # Lightweight presence check — full MCP JSON-RPC is session-based;
        # we still produce a diagrams.net URL for the product path.
        proc = subprocess.run(
            ["npx", "-y", "@drawio/mcp", "--help"],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        available = proc.returncode == 0 or "draw" in (proc.stdout + proc.stderr).lower()
        if not available:
            return {"npx_checked": True, "package_ready": False}
        return {"npx_checked": True, "package_ready": True}
    except (OSError, subprocess.TimeoutExpired):
        return {"npx_checked": True, "package_ready": False, "error": "timeout_or_os"}


def run_drawio_mcp_for_visual(
    *,
    structured: dict[str, Any] | None,
    goal: str = "",
    try_npx: bool = True,
) -> dict[str, Any]:
    """
    Produce draw.io connector output for the visual summary.

    Returns a tool-result shaped dict always (success or soft skip).
    """
    mermaid, kind = mermaid_from_structured(structured)
    if not mermaid:
        return {
            "status": "skipped",
            "reason": "no_diagram_structure",
            "detail": (
                "No process_flow, sequence, or ordered steps in the handoff "
                "to send to draw.io."
            ),
            "provider": "draw.io",
        }

    title = (goal or "Sourcebook diagram").strip()[:80] or "Sourcebook diagram"
    edit_url = drawio_edit_url(mermaid, title=title)
    b64 = base64.urlsafe_b64encode(mermaid.encode("utf-8")).decode("ascii").rstrip("=")
    preview_url = f"https://mermaid.ink/svg/{b64}"

    result: dict[str, Any] = {
        "status": "ok",
        "provider": "draw.io",
        "connector_id": "mcp_drawio",
        "diagram_kind": kind,
        "mermaid": mermaid,
        "edit_url": edit_url,
        "preview_url": preview_url,
        "source": "sourcebook_drawio_mcp",
    }
    if try_npx:
        npx_info = _try_npx_drawio_mcp(mermaid)
        if npx_info:
            result["npx"] = npx_info
    return result


def attach_drawio_to_spec(spec: dict[str, Any], drawio_result: dict[str, Any]) -> dict[str, Any]:
    """Merge draw.io MCP result into presentation_spec.meta."""
    out = dict(spec)
    meta = dict(out.get("meta") or {}) if isinstance(out.get("meta"), dict) else {}
    if drawio_result.get("status") == "ok":
        meta["drawio"] = {
            "mermaid": drawio_result.get("mermaid"),
            "edit_url": drawio_result.get("edit_url"),
            "preview_url": drawio_result.get("preview_url"),
            "diagram_kind": drawio_result.get("diagram_kind"),
            "connector_id": "mcp_drawio",
        }
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
