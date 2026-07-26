"""Progressive panel assembly for Visual Summary (P0 + P2).

Assembles layout outline entries one-by-one and notifies the caller after
each panel so SSE can paint the Visual tab without waiting for the full board.

Two-phase panels for diagram types:
  1. text  — key_points / steps / summary from the same section (instant card)
  2. figure — flow_diagram / sequence_diagram upgrade when graph data exists
"""

from __future__ import annotations

from typing import Any, Callable

from app.agents.visual_summary.planning.layout_stabilize import (
    sanitize_presentation_profile,
)
from app.agents.visual_summary.render.assemble import assemble_blocks

# Block types that benefit from a text-first paint before the figure lands.
FIGURE_BLOCK_TYPES = frozenset(
    {
        "flow_diagram",
        "sequence_diagram",
        "compare_paths",
        "mcp_diagram",
    }
)

# Minimum outline length before progressive path is worth the extra events.
_MIN_OUTLINE_FOR_PROGRESSIVE = 2

PanelCallback = Callable[[dict[str, Any]], None]


def should_use_progressive_render(plan: dict[str, Any] | None) -> bool:
    """True when the plan has enough outline rows to stream panel-by-panel."""
    if not isinstance(plan, dict):
        return False
    outline = plan.get("block_outline") or []
    if not isinstance(outline, list):
        return False
    typed = [
        e
        for e in outline
        if isinstance(e, dict) and str(e.get("type") or "").strip()
    ]
    return len(typed) >= _MIN_OUTLINE_FOR_PROGRESSIVE


def _profile_and_title(
    plan: dict[str, Any],
    *,
    goal: str,
    workspace_name: str,
    structured: dict[str, Any],
) -> tuple[str, str, str]:
    profile = sanitize_presentation_profile(
        str(plan.get("presentation_profile") or ""),
        goal=goal,
        fallback="workspace_derived",
    )
    summary = str(structured.get("summary") or "").strip()
    plain = summary or (goal or "")[:200]
    title = (workspace_name or "").strip() or profile.replace("_", " ").title()
    if goal and len(goal.strip()) < 80:
        title = goal.strip()[:80]
    return profile, title[:120], plain[:600]


def empty_partial_spec(
    plan: dict[str, Any],
    *,
    goal: str,
    workspace_name: str = "",
    structured: dict[str, Any] | None = None,
    source_files: list[str] | None = None,
    expected_count: int = 0,
) -> dict[str, Any]:
    """Shell presentation_spec before any panel is ready."""
    structured = structured if isinstance(structured, dict) else {}
    profile, title, plain = _profile_and_title(
        plan, goal=goal, workspace_name=workspace_name, structured=structured
    )
    return {
        "type": "generative_ui",
        "title": title,
        "plain_summary": plain,
        "presentation_profile": profile,
        "blocks": [],
        "source_files": list(source_files or []),
        "status": "streaming",
        "expected_count": expected_count,
        "ready_count": 0,
        "assembly_meta": {
            "assembled_blocks": [],
            "dropped_blocks": [],
            "render_fallback_used": False,
            "progressive": True,
        },
    }


def _text_first_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Demote diagram outline rows to a text block for the first paint."""
    e = dict(entry)
    btype = str(e.get("type") or "").strip()
    if btype not in FIGURE_BLOCK_TYPES:
        return e
    heading = str(e.get("title") or "").lower()
    if any(
        k in heading
        for k in ("step", "transaction", "procedure", "checklist", "how to")
    ):
        e["type"] = "steps"
        e["source_hint"] = "ordered_actions"
    else:
        e["type"] = "key_points"
        e["source_hint"] = "key_points"
    return e


def _block_has_figure_payload(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return False
    btype = str(block.get("type") or "")
    if btype == "flow_diagram":
        nodes = block.get("nodes") or []
        edges = block.get("edges") or []
        return len(nodes) >= 2 and len(edges) >= 1
    if btype == "sequence_diagram":
        actors = block.get("actors") or []
        messages = block.get("messages") or []
        return len(actors) >= 2 and len(messages) >= 1
    if btype == "compare_paths":
        paths = block.get("paths") or []
        ok = 0
        for p in paths if isinstance(paths, list) else []:
            if not isinstance(p, dict):
                continue
            if len(p.get("nodes") or []) >= 2 and len(p.get("edges") or []) >= 1:
                ok += 1
        return ok >= 2
    if btype == "mcp_diagram":
        return bool(block.get("mermaid") or block.get("png_data_url") or block.get("preview_url"))
    return False


def merge_prose_into_figure(
    prose: dict[str, Any],
    figure: dict[str, Any],
) -> dict[str, Any]:
    """Composite panel: keep teaching text when upgrading to a diagram."""
    out = dict(figure)
    # Prefer figure type/title; keep prose bullets/body for the UI companion.
    if prose.get("items") and not out.get("items"):
        out["items"] = list(prose["items"])
    if prose.get("body") and not out.get("body") and not out.get("items"):
        out["body"] = prose["body"]
    if not out.get("title") and prose.get("title"):
        out["title"] = prose["title"]
    if not out.get("tags") and prose.get("tags"):
        out["tags"] = prose["tags"]
    # Keep study-sheet section tag from prose when figure omitted it.
    prose_tags = prose.get("tags") if isinstance(prose.get("tags"), list) else []
    fig_tags = list(out.get("tags") or []) if isinstance(out.get("tags"), list) else []
    for t in prose_tags:
        if str(t).startswith("__section:") and t not in fig_tags:
            fig_tags = [t, *fig_tags]
    if fig_tags:
        out["tags"] = fig_tags[:6]
    if prose.get("width") in ("full", "half") and out.get("width") not in ("full", "half"):
        out["width"] = prose["width"]
    return out


def _assemble_one(
    entry: dict[str, Any],
    structured: dict[str, Any],
) -> dict[str, Any] | None:
    blocks, _dropped = assemble_blocks([entry], structured, max_blocks=1)
    if not blocks:
        return None
    return blocks[0].model_dump()


def _panel_index(entry: dict[str, Any], fallback: int) -> int:
    for key in ("panel_index", "section_index"):
        raw = entry.get(key)
        if raw is None:
            continue
        try:
            n = int(raw)
            if n >= 1:
                return n
        except (TypeError, ValueError):
            continue
    return fallback


def _upsert_block_by_index(
    blocks: list[dict[str, Any]],
    block: dict[str, Any],
    panel_index: int,
) -> list[dict[str, Any]]:
    """Replace or append a block keyed by __section:N (or append if untagged)."""
    tag = f"__section:{panel_index}"
    out = list(blocks)
    for i, existing in enumerate(out):
        tags = existing.get("tags") if isinstance(existing, dict) else None
        if isinstance(tags, list) and tag in [str(t) for t in tags]:
            out[i] = block
            return out
    # Fallback: match by position among section-tagged blocks
    out.append(block)
    # Keep stable order by panel index when tags are present
    def sort_key(b: dict[str, Any]) -> tuple[int, str]:
        tags = b.get("tags") if isinstance(b, dict) else None
        if isinstance(tags, list):
            for t in tags:
                s = str(t)
                if s.startswith("__section:"):
                    try:
                        return (int(s.split(":", 1)[1]), str(b.get("title") or ""))
                    except ValueError:
                        pass
        return (10_000, str(b.get("title") or ""))

    out.sort(key=sort_key)
    return out


def progressive_assemble_presentation(
    plan: dict[str, Any],
    structured: dict[str, Any],
    *,
    goal: str = "",
    workspace_name: str = "",
    source_files: list[str] | None = None,
    on_panel: PanelCallback | None = None,
) -> dict[str, Any]:
    """
    Assemble panels one-by-one; call ``on_panel`` after each text/figure paint.

    Callback payload:
      phase: "text" | "figure" | "complete"
      panel_index: int
      block: dict | None
      presentation_spec: full partial snapshot
      expected_count / ready_count
    """
    outline_raw = plan.get("block_outline") or []
    outline = [
        e
        for e in outline_raw
        if isinstance(e, dict) and str(e.get("type") or "").strip()
    ]
    expected = len(outline)
    spec = empty_partial_spec(
        plan,
        goal=goal,
        workspace_name=workspace_name,
        structured=structured,
        source_files=source_files,
        expected_count=expected,
    )
    assembled_types: list[str] = []
    dropped: list[dict[str, str]] = []

    def emit(phase: str, panel_index: int, block: dict[str, Any] | None) -> None:
        if on_panel is None:
            return
        on_panel(
            {
                "phase": phase,
                "panel_index": panel_index,
                "block": block,
                "presentation_spec": dict(spec),
                "expected_count": expected,
                "ready_count": int(spec.get("ready_count") or 0),
            }
        )

    for i, entry in enumerate(outline, start=1):
        panel_n = _panel_index(entry, i)
        original_type = str(entry.get("type") or "").strip()
        wants_figure = original_type in FIGURE_BLOCK_TYPES

        # Phase 1: text-first (for figures) or full non-figure block
        first_entry = _text_first_entry(entry) if wants_figure else entry
        text_block = _assemble_one(first_entry, structured)
        if text_block is None and wants_figure:
            # Figure demotion failed — try original as text-ish fallback once more
            text_block = _assemble_one(
                {
                    **entry,
                    "type": "summary",
                    "source_hint": "summary",
                },
                structured,
            )

        if text_block is None:
            dropped.append(
                {
                    "type": original_type or "block",
                    "reason": "progressive_assemble_empty",
                }
            )
            continue

        blocks = list(spec.get("blocks") or [])
        blocks = _upsert_block_by_index(blocks, text_block, panel_n)
        spec["blocks"] = blocks
        spec["ready_count"] = len(blocks)
        assembled_types = [str(b.get("type") or "") for b in blocks]
        spec["assembly_meta"] = {
            "assembled_blocks": assembled_types,
            "dropped_blocks": list(dropped),
            "render_fallback_used": False,
            "progressive": True,
        }
        emit("text", panel_n, text_block)

        # Phase 2: figure upgrade — merge prose + diagram (never drop text)
        if wants_figure:
            figure_block = _assemble_one(entry, structured)
            if figure_block and _block_has_figure_payload(figure_block):
                composite = merge_prose_into_figure(text_block, figure_block)
                blocks = _upsert_block_by_index(
                    list(spec.get("blocks") or []), composite, panel_n
                )
                spec["blocks"] = blocks
                spec["ready_count"] = len(blocks)
                assembled_types = [str(b.get("type") or "") for b in blocks]
                spec["assembly_meta"] = {
                    "assembled_blocks": assembled_types,
                    "dropped_blocks": list(dropped),
                    "render_fallback_used": False,
                    "progressive": True,
                    "composite_panels": True,
                }
                emit("figure", panel_n, composite)

    spec["status"] = "complete"
    spec["ready_count"] = len(spec.get("blocks") or [])
    if not spec.get("blocks"):
        # Caller should fall back to batch render_ui / LLM path
        return {
            "type": "generative_ui",
            "title": spec.get("title") or "Visual summary",
            "plain_summary": spec.get("plain_summary") or "",
            "presentation_profile": spec.get("presentation_profile"),
            "blocks": [],
            "source_files": list(source_files or []),
            "status": "empty",
            "assembly_meta": {
                "assembled_blocks": [],
                "dropped_blocks": dropped,
                "render_fallback_used": False,
                "progressive": True,
            },
        }

    emit("complete", 0, None)
    return spec
