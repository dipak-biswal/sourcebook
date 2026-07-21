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
    if run.presentation_spec:
        return step_index
    if not should_offer_presentation(
        goal=run.goal or "",
        final_answer=run.final_answer,
        status=run.status,
    ):
        return step_index

    run.status = "waiting_approval"
    run.pending_tool = {
        "id": str(uuid.uuid4()),
        "name": PRESENTATION_TOOL,
        "kind": "presentation",
        "args": {
            "goal": run.goal,
            "answer_preview": (run.final_answer or "")[:240],
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
