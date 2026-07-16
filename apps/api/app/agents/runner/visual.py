"""Visual Summary / presentation helpers (no dependency on the tool loop)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.runner.constants import PRESENTATION_TOOL
from app.agents.runner.events import EventCallback, _append_step, _emit
from app.agents.visual_tools import VISUAL_SUMMARY_AGENT_LABEL
from app.config import settings
from app.models import AgentRun, Document, Workspace
from app.presentation.answer import resolve_presentation_answer
from app.presentation.context import PresentationContext
from app.presentation.evidence import (
    collect_evidence_from_steps,
    serialize_agent_evidence,
)
from app.presentation.handoff import resolve_structured_content
from app.presentation.workspace_context import resolve_workspace_context


def _is_presentation_pending(pending: dict[str, Any] | None) -> bool:
    if not pending:
        return False
    return (
        pending.get("name") == PRESENTATION_TOOL
        or pending.get("kind") == "presentation"
    )


def _presentation_context_for_run(db: Session, run: AgentRun) -> PresentationContext:
    ws = db.get(Workspace, run.workspace_id)
    filenames = [
        row[0]
        for row in db.query(Document.filename)
        .filter(Document.workspace_id == run.workspace_id)
        .order_by(Document.created_at.desc())
        .limit(20)
        .all()
    ]
    raw_tags = ws.tags if ws and isinstance(ws.tags, list) else []
    tags = [str(t).strip() for t in raw_tags if t and str(t).strip()]
    steps = sorted(run.steps or [], key=lambda s: s.step_index)
    agent_evidence = collect_evidence_from_steps(steps)
    narrative = resolve_presentation_answer(
        final_answer=run.final_answer,
        steps=steps,
    )
    goal = run.goal or ""
    user_id = run.user_id or uuid.UUID(int=0)
    packet = getattr(run, "_workspace_context", None) or resolve_workspace_context(
        db, run.workspace_id
    )
    run._workspace_context = packet  # type: ignore[attr-defined]
    structured_content, _source = resolve_structured_content(
        narrative,
        goal=goal,
        db=db,
        user_id=user_id,
        workspace_id=run.workspace_id,
        workspace_packet=packet,
        evidence=agent_evidence,
    )
    return PresentationContext(
        workspace_id=run.workspace_id,
        user_id=user_id,
        goal=goal,
        final_answer=narrative,
        workspace_name=ws.name if ws else "",
        workspace_description=(ws.description or "") if ws else "",
        workspace_tags=tags,
        document_filenames=filenames,
        agent_evidence=agent_evidence,
        structured_content=structured_content,
        workspace_packet=packet.to_dict(),
    )


def _visual_summary_handoff_message(ctx: PresentationContext) -> str:
    structured = ctx.structured_content or {}
    kp = len(structured.get("key_points") or [])
    faq = len(structured.get("faq") or [])
    sections = len(structured.get("sections") or [])
    return (
        "MAIN AGENT HANDOFF (complete — do not re-analyze documents)\n\n"
        f"User goal:\n{ctx.goal}\n\n"
        "Structured content was extracted from the main agent answer for planning.\n"
        f"- Summary: {(structured.get('summary') or '')[:240]}\n"
        f"- Key points: {kp}\n"
        f"- FAQ items: {faq}\n"
        f"- Sections: {sections}\n\n"
        "Call plan_layout (uses structured input internally), review the plan, "
        "then call render_ui with the layout plan JSON string."
    )


_VISUAL_TOOL_LLM_FIELDS = (
    "model",
    "prompt",
    "llm_output",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)


def _visual_tool_result_input(tool_name: str, args: Any, result: Any) -> Any:
    """Persist embedded LLM metadata on visual tool_result steps for trace + totals."""
    payload = dict(args or {}) if isinstance(args, dict) else {}
    if tool_name not in ("plan_layout", "render_ui") or not isinstance(result, dict):
        return payload
    for key in _VISUAL_TOOL_LLM_FIELDS:
        value = result.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _accumulate_visual_tool_tokens(
    result: Any,
    *,
    prompt_tokens_total: int,
    completion_tokens_total: int,
    total_tokens_acc: int,
) -> tuple[int, int, int]:
    if not isinstance(result, dict):
        return prompt_tokens_total, completion_tokens_total, total_tokens_acc
    prompt = int(result.get("prompt_tokens") or 0)
    completion = int(result.get("completion_tokens") or 0)
    total = int(result.get("total_tokens") or 0) or (prompt + completion)
    if prompt <= 0 and completion <= 0 and total <= 0:
        return prompt_tokens_total, completion_tokens_total, total_tokens_acc
    return (
        prompt_tokens_total + prompt,
        completion_tokens_total + completion,
        total_tokens_acc + total,
    )


def _visual_tool_call_input(
    tool_name: str,
    args: Any,
    *,
    ctx: PresentationContext | None,
) -> Any:
    """Record compact structured handoff on plan_layout tool calls (not raw answer)."""
    if tool_name != "plan_layout" or ctx is None:
        return args
    payload = dict(args or {}) if isinstance(args, dict) else {"notes": args}
    payload["structured_handoff"] = ctx.structured_content
    payload["goal"] = ctx.goal
    return payload


def _spec_from_render_ui_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    spec = result.get("spec")
    if isinstance(spec, dict) and not spec.get("error"):
        return spec
    return None


def _extract_render_ui_spec(run: AgentRun) -> dict[str, Any] | None:
    for step in reversed(sorted(run.steps or [], key=lambda s: s.step_index)):
        if step.type != "tool_result" or step.tool_name != "render_ui":
            continue
        spec = _spec_from_render_ui_result(step.output)
        if spec:
            return spec
    return None


def _is_generative_ui_output(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "generative_ui"
        and isinstance(value.get("title"), str)
    )


def _has_presentation_step(run: AgentRun) -> bool:
    return any(
        s.type == "presentation" or _is_generative_ui_output(s.output)
        for s in (run.steps or [])
    )


def _apply_render_ui_result(
    run: AgentRun,
    *,
    tool_name: str,
    result: Any,
    on_event: EventCallback = None,
) -> bool:
    """Persist generative UI as soon as render_ui succeeds."""
    if tool_name != "render_ui":
        return False
    spec = _spec_from_render_ui_result(result)
    if not spec:
        return False
    run.presentation_spec = spec
    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status=run.status,
        presentation_spec=spec,
        final_answer=run.final_answer,
    )
    return True


def _attach_presentation_step(
    db: Session,
    run: AgentRun,
    *,
    spec: dict[str, Any],
    step_index: int,
    agent_evidence: Any,
    build_meta: dict[str, Any] | None = None,
    on_event: EventCallback = None,
) -> int:
    meta = build_meta or {}
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="presentation",
        tool_name="generative_ui",
        input={
            "agent": VISUAL_SUMMARY_AGENT_LABEL,
            "prompt": meta.get("prompt"),
            "llm_output": meta.get("llm_output"),
            "messages": meta.get("messages"),
            "model": meta.get("model") or settings.visual_summary_model,
            "prompt_tokens": meta.get("prompt_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "total_tokens": meta.get("total_tokens"),
            "agent_evidence": serialize_agent_evidence(agent_evidence),
        },
        output=spec,
        on_event=on_event,
    )
    _emit(
        on_event,
        "presentation",
        run_id=str(run.id),
        presentation_profile=spec.get("presentation_profile"),
    )
    return step_index


def _finalize_visual_summary_run(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    spec = run.presentation_spec if isinstance(run.presentation_spec, dict) else None
    if not spec:
        spec = _extract_render_ui_spec(run)
    if not spec:
        return step_index

    run.presentation_spec = spec
    plain = spec.get("plain_summary")
    if plain and (not run.final_answer or run.final_answer == "(no final answer)"):
        run.final_answer = str(plain)

    if _has_presentation_step(run):
        return step_index

    ctx = _presentation_context_for_run(db, run)
    return _attach_presentation_step(
        db,
        run,
        spec=spec,
        step_index=step_index,
        agent_evidence=ctx.agent_evidence,
        on_event=on_event,
    )
