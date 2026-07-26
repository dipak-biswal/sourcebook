"""Main-agent run finalization: answer selection and the presentation offer."""

from __future__ import annotations

import uuid

from langchain_core.messages import BaseMessage
from sqlalchemy.orm import Session

from app.agents.main.runner.constants import PRESENTATION_TOOL
from app.agents.main.runner.events import EventCallback, _append_step, _emit
from app.agents.main.runner.synthesis import (
    _prefer_gen_ui_summary,
    _synthesize_final_answer,
    _weak_final_answer,
)
from app.models import AgentRun
from app.agents.visual_summary.planning.planner import should_offer_presentation


def _finalize_completed_run(
    db: Session,
    run: AgentRun,
    *,
    messages: list[BaseMessage],
    fallback_answer: str,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """Set final answer and attach auto-generated presentation when appropriate."""
    answer = _prefer_gen_ui_summary(messages, fallback_answer)
    if _weak_final_answer(answer):
        synthesized = _synthesize_final_answer(db, run, messages)
        if synthesized:
            answer = synthesized
            step_index += 1
            _append_step(
                db,
                run,
                step_index=step_index,
                type="synthesis",
                input=getattr(run, "_synthesis_trace_input", None),
                output=answer,
                on_event=on_event,
            )
    run.final_answer = answer
    # Ensure study-sheet sections are split even if mid-stream missed them
    # (e.g. synthesis path or single-shot final without streaming).
    try:
        from app.agents.main.runner.section_stream import (
            SectionStreamTracker,
            attach_streamed_sections_to_run,
            should_stream_sections,
        )

        if should_stream_sections(run.goal or "", text_so_far=answer or ""):
            from app.agents.main.runner.section_stream import maybe_paint_early_visual

            existing = getattr(run, "_streamed_sections", None)
            if not existing:
                tracker = SectionStreamTracker(
                    on_event=on_event,
                    run_id=str(run.id),
                    goal=run.goal or "",
                )
                tracker.finish(answer or "")
                attach_streamed_sections_to_run(run, tracker)
                maybe_paint_early_visual(
                    db, run, tracker, on_event=on_event, force_complete=True
                )
            else:
                # Re-paint complete board from sections already on the run.
                tracker = SectionStreamTracker(
                    on_event=on_event,
                    run_id=str(run.id),
                    goal=run.goal or "",
                )
                # Reconstruct tracker sections from stored structured shape.
                for i, s in enumerate(existing, start=1):
                    if not isinstance(s, dict):
                        continue
                    tracker._sections.append(
                        {
                            "index": i,
                            "heading": s.get("heading") or f"{i}.",
                            "title": str(s.get("heading") or "").split(".", 1)[-1].strip(),
                            "body": s.get("body") or "",
                            "bullets": s.get("bullets") or [],
                        }
                    )
                    tracker._emitted.add(i)
                maybe_paint_early_visual(
                    db, run, tracker, on_event=on_event, force_complete=True
                )
    except Exception:
        pass
    run.status = "completed"
    return _offer_presentation_if_needed(
        db,
        run,
        step_index=step_index,
        on_event=on_event,
    )


def _offer_presentation_if_needed(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """Pause for human-in-the-loop before building generative UI."""
    # Early visual is a live preview only. For teaching answers, immediately
    # run the full visual pipeline (higher quality) without an extra HITL click.
    if isinstance(run.presentation_spec, dict):
        blocks = run.presentation_spec.get("blocks") or []
        early = bool(
            run.presentation_spec.get("early_visual")
            or (run.presentation_spec.get("assembly_meta") or {}).get("early_visual")
        )
        if early and isinstance(blocks, list) and len(blocks) >= 1:
            try:
                from app.agents.main.runner.early_visual import (
                    upgrade_early_visual_to_full,
                )

                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status="running",
                    message="Upgrading preview board to full visual summary",
                    presentation_spec=run.presentation_spec,
                    final_answer=run.final_answer,
                )
                upgraded = upgrade_early_visual_to_full(
                    db,
                    run,
                    step_index=step_index,
                    on_event=on_event,
                )
                return max(
                    step_index,
                    max(
                        (s.step_index for s in (upgraded.steps or [])),
                        default=step_index,
                    ),
                )
            except Exception:
                # Fall back to early board + MCP enrich if full upgrade fails.
                try:
                    from app.agents.main.runner.early_visual import (
                        enrich_early_visual_with_mcp,
                    )

                    run.presentation_spec = {
                        **(run.presentation_spec or {}),
                        "status": "complete",
                    }
                    enrich_early_visual_with_mcp(
                        db,
                        run,
                        on_event=on_event,
                        user_id=run.user_id,
                    )
                except Exception:
                    pass
                if run.status == "running":
                    run.status = "completed"
                    run.pending_tool = None
                    db.commit()
                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status=run.status,
                    presentation_spec=run.presentation_spec,
                    final_answer=run.final_answer,
                    pending_tool=None,
                )
                return step_index
        # Non-early full spec already present
        if blocks and not early:
            return step_index
    if not should_offer_presentation(
        goal=run.goal or "",
        final_answer=run.final_answer,
        status=run.status,
    ):
        return step_index

    # Surface MCP connectors the user can opt into for Visual Summary.
    from app.agents.connectors import list_mcp_connectors
    from app.mcp.drawio import enabled_mcp_ids_from_run

    available_mcp = [
        {
            "id": c["id"],
            "name": c["name"],
            "icon": c.get("icon") or "tool",
            "phase": c.get("phase") or "visual",
        }
        for c in list_mcp_connectors()
        if c.get("status") != "disabled"
    ]
    # Prefer run-start toggles; otherwise default available MCPs ON for visual.
    preselected = enabled_mcp_ids_from_run(run)
    if not preselected:
        preselected = [c["id"] for c in available_mcp]

    run.status = "waiting_approval"
    run.pending_tool = {
        "id": str(uuid.uuid4()),
        "name": PRESENTATION_TOOL,
        "kind": "presentation",
        "args": {
            "goal": run.goal,
            "answer_preview": (run.final_answer or "")[:240],
            "available_mcp": available_mcp,
            "preselected_mcp_ids": preselected,
        },
    }
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="approval",
        tool_name=PRESENTATION_TOOL,
        input=run.pending_tool.get("args"),
        output={
            "status": "waiting_approval",
            "kind": "presentation",
            "available_mcp": available_mcp,
            "preselected_mcp_ids": preselected,
        },
        on_event=on_event,
    )
    _emit(
        on_event,
        "presentation_offer",
        run_id=str(run.id),
        status="waiting_approval",
        pending_tool=run.pending_tool,
        final_answer=run.final_answer,
    )
    return step_index
