"""Code-only early Visual Summary while the main agent still streams sections.

When study-sheet sections close mid-answer, assemble panels immediately and
emit presentation_panel_ready so the Visual tab can paint in parallel with
the Answer tab — no plan_layout LLM, no presentation HITL required for
teaching goals that already produced a board.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.main.runner.events import EventCallback, _emit
from app.agents.visual_summary.planning.study_sheet import (
    STUDY_SHEET_PROFILE,
    build_topic_study_sheet_plan,
    infer_section_block_type,
    is_topic_study_sheet_goal,
)
from app.agents.visual_summary.streaming.progressive import (
    progressive_assemble_presentation,
    should_use_progressive_render,
)
from app.models import AgentRun


def _structured_from_streamed(sections: list[dict[str, Any]], goal: str) -> dict[str, Any]:
    clean: list[dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        heading = str(s.get("heading") or "").strip()
        body = str(s.get("body") or "").strip()
        bullets = s.get("bullets") if isinstance(s.get("bullets"), list) else []
        bullets = [str(b).strip() for b in bullets if str(b).strip()]
        if heading and (body or bullets):
            clean.append({"heading": heading, "body": body, "bullets": bullets})
    summary = ""
    if clean:
        summary = (clean[0].get("body") or " ".join(clean[0].get("bullets") or [])[:200])
    return {
        "summary": summary[:600],
        "key_points": [],
        "faq": [],
        "themes": [],
        "sections": clean,
    }


def _fallback_plan(structured: dict[str, Any], goal: str) -> dict[str, Any] | None:
    """Minimal outline when study-sheet planner declines (too few sections)."""
    sections = structured.get("sections") or []
    if len(sections) < 1:
        return None
    outline: list[dict[str, Any]] = []
    components: list[str] = []
    for i, sec in enumerate(sections, start=1):
        if not isinstance(sec, dict):
            continue
        btype = infer_section_block_type(sec)
        title = str(sec.get("heading") or f"{i}. Section")[:120]
        from app.agents.visual_summary.planning.study_sheet import (
            _source_hint_for_type,
        )

        outline.append(
            {
                "type": btype,
                "title": title,
                "purpose": f"Early panel {i}",
                "source_hint": _source_hint_for_type(btype),
                "width": "full"
                if btype
                in (
                    "table",
                    "comparison",
                    "compare_paths",
                    "flow_diagram",
                    "sequence_diagram",
                    "steps",
                )
                else "half",
                "section_index": i,
                "panel_index": i,
                "affordance": "study_sheet_section",
            }
        )
        if btype not in components:
            components.append(btype)
    if not outline:
        return None
    return {
        "presentation_profile": STUDY_SHEET_PROFILE,
        "components": components,
        "block_outline": outline,
        "rationale": "Early visual from streamed sections",
        "ui_intent": {"mode": STUDY_SHEET_PROFILE, "section_count": len(outline)},
    }


def refresh_early_visual(
    db: Session,
    run: AgentRun,
    *,
    sections: list[dict[str, Any]],
    on_event: EventCallback = None,
    force_complete: bool = False,
) -> dict[str, Any] | None:
    """
    Rebuild presentation_spec from streamed sections and notify the client.

    Mid-stream paints are throttled (first section, every 2nd section, or when
    force_complete) so we do not re-assemble the full board on every close.

    Returns the new spec or None when nothing to paint.
    """
    if not sections or len(sections) < 1:
        return None
    goal = run.goal or ""
    # Only for teaching / study goals (avoid random dashboards mid-run).
    if not (
        is_topic_study_sheet_goal(goal)
        or __import__("re").search(
            r"\b(explain|teach|learn|study\s*sheet|walk\s*me\s*through)\b",
            goal,
            __import__("re").I,
        )
    ):
        return None

    n = len(sections)
    # Throttle mid-stream: paint section 1, then even counts (2, 4, …), always on complete.
    # Odd counts after the first still advance the counter but skip full reassemble.
    if not force_complete and n > 1 and n % 2 == 1:
        run._early_visual_section_count = n  # type: ignore[attr-defined]
        return (
            run.presentation_spec
            if isinstance(run.presentation_spec, dict)
            else None
        )
    if not force_complete and n == int(
        getattr(run, "_early_visual_section_count", 0) or 0
    ):
        return (
            run.presentation_spec
            if isinstance(run.presentation_spec, dict)
            else None
        )

    structured = _structured_from_streamed(sections, goal)
    if len(structured["sections"]) < 1:
        return None

    plan = build_topic_study_sheet_plan(structured, goal=goal)
    if plan is None:
        plan = _fallback_plan(structured, goal)
    if not plan or not should_use_progressive_render(plan):
        # Single section: still paint one panel.
        if plan is None:
            plan = _fallback_plan(structured, goal)
        if not plan:
            return None

    prev_count = 0
    prev = run.presentation_spec if isinstance(run.presentation_spec, dict) else None
    if prev and isinstance(prev.get("blocks"), list):
        prev_count = len(prev["blocks"])

    skeleton_sent = bool(getattr(run, "_early_visual_skeleton_sent", False))

    def on_panel(payload: dict[str, Any]) -> None:
        phase = str(payload.get("phase") or "")
        spec = payload.get("presentation_spec")
        if not isinstance(spec, dict):
            return
        if force_complete:
            spec = dict(spec)
            spec["status"] = "complete"
        else:
            spec = dict(spec)
            spec["status"] = "streaming"
            spec["early_visual"] = True
        run.presentation_spec = spec
        if phase == "complete":
            return
        _emit(
            on_event,
            "presentation_panel_ready",
            run_id=str(run.id),
            phase=phase,
            panel_index=payload.get("panel_index"),
            block=payload.get("block"),
            expected_count=payload.get("expected_count"),
            ready_count=payload.get("ready_count"),
            presentation_spec=spec,
            early_visual=True,
        )
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            presentation_spec=spec,
            final_answer=run.final_answer,
        )

    if not skeleton_sent:
        outline = [
            {
                "type": str(e.get("type")),
                "title": str(e.get("title") or ""),
                "width": e.get("width") or None,
            }
            for e in (plan.get("block_outline") or [])
            if isinstance(e, dict) and e.get("type")
        ]
        _emit(
            on_event,
            "presentation_skeleton",
            run_id=str(run.id),
            presentation_profile=plan.get("presentation_profile"),
            outline=outline,
            early_visual=True,
        )
        run._early_visual_skeleton_sent = True  # type: ignore[attr-defined]

    ws_name = ""
    try:
        from app.models import Workspace

        ws = db.get(Workspace, run.workspace_id) if db is not None else None
        ws_name = (ws.name if ws else "") or ""
    except Exception:
        pass

    spec = progressive_assemble_presentation(
        plan,
        structured,
        goal=goal,
        workspace_name=ws_name,
        on_panel=on_panel,
    )
    if not isinstance(spec, dict) or not (spec.get("blocks") or []):
        return None

    if force_complete:
        spec["status"] = "complete"
        spec["early_visual"] = True
    else:
        spec["status"] = "streaming"
        spec["early_visual"] = True

    # Stamp assembly meta
    meta = dict(spec.get("assembly_meta") or {})
    meta["early_visual"] = True
    meta["from_streamed_sections"] = True
    spec["assembly_meta"] = meta

    run.presentation_spec = spec
    run._early_visual_section_count = n  # type: ignore[attr-defined]
    try:
        if db is not None:
            db.add(run)
            db.commit()
    except Exception:
        if db is not None:
            db.rollback()

    # If no new panels were emitted (rebuild same count), still push status once.
    new_count = len(spec.get("blocks") or [])
    if new_count <= prev_count and force_complete:
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            presentation_spec=spec,
            final_answer=run.final_answer,
        )
    return spec


def early_visual_is_ready(spec: dict[str, Any] | None, *, min_blocks: int = 2) -> bool:
    if not isinstance(spec, dict):
        return False
    blocks = spec.get("blocks") or []
    return isinstance(blocks, list) and len(blocks) >= min_blocks


def enrich_early_visual_with_mcp(
    db: Session,
    run: AgentRun,
    *,
    on_event: EventCallback = None,
    user_id: Any = None,
) -> int:
    """
    Optional draw.io / Mermaid enrich after early visual (no HITL).

    Attaches mermaid/PNG onto existing panels — never replaces teaching text.
    Returns number of panels enriched. Best-effort; never raises to caller.
    """
    try:
        from app.mcp.drawio import (
            enabled_mcp_ids_from_run,
            render_section_diagrams_via_mcp,
        )
        from app.agents.visual_summary.planning.section_diagrams import (
            author_section_diagrams,
        )
        from app.agents.visual_summary.pipeline import _apply_section_diagrams_to_spec
    except Exception:
        return 0

    if "mcp_drawio" not in enabled_mcp_ids_from_run(run):
        return 0
    spec = run.presentation_spec
    if not isinstance(spec, dict) or not (spec.get("blocks") or []):
        return 0

    sections_raw = getattr(run, "_streamed_sections", None)
    if not sections_raw and isinstance(run.run_options, dict):
        sections_raw = run.run_options.get("streamed_sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        return 0

    # (panel_index, section_dict) — 1-based to match __section:N tags
    panel_sections: list[tuple[int, dict[str, Any]]] = []
    for i, s in enumerate(sections_raw, start=1):
        if isinstance(s, dict):
            panel_sections.append((i, s))
    if not panel_sections:
        return 0

    max_sections = 8
    try:
        from app.config import settings

        max_sections = int(getattr(settings, "mcp_drawio_max_sections", 8) or 8)
    except Exception:
        pass
    panel_sections = panel_sections[:max_sections]

    try:
        authored = author_section_diagrams(
            panel_sections,
            goal=run.goal or "",
            db=db,
            user_id=user_id or run.user_id,
            workspace_id=run.workspace_id,
        )
    except Exception:
        return 0
    if not authored:
        return 0

    try:
        sections_mermaid = {
            idx: (data["mermaid"], data["diagram_kind"])
            for idx, data in authored.items()
            if isinstance(data, dict) and data.get("mermaid")
        }
        if not sections_mermaid:
            return 0
        rendered = render_section_diagrams_via_mcp(sections_mermaid)
        new_spec, applied = _apply_section_diagrams_to_spec(spec, rendered)
    except Exception:
        return 0

    if not applied:
        return 0

    meta = dict(new_spec.get("assembly_meta") or {})
    meta["early_visual"] = True
    meta["mcp_enriched"] = True
    meta["mcp_panels"] = applied
    new_spec["assembly_meta"] = meta
    new_spec["status"] = "complete"
    new_spec["early_visual"] = True
    run.presentation_spec = new_spec
    try:
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()

    _emit(
        on_event,
        "presentation_panel_ready",
        run_id=str(run.id),
        phase="mcp_enrich",
        ready_count=len(new_spec.get("blocks") or []),
        expected_count=len(new_spec.get("blocks") or []),
        presentation_spec=new_spec,
        early_visual=True,
        mcp_enriched=True,
    )
    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status=run.status,
        presentation_spec=new_spec,
        final_answer=run.final_answer,
    )
    _emit(
        on_event,
        "presentation",
        run_id=str(run.id),
        presentation_spec=new_spec,
        early_visual=True,
        mcp_enriched=True,
    )
    return applied
