"""Visual Summary / presentation helpers (no dependency on the tool loop)."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.main.runner.constants import PRESENTATION_TOOL
from app.agents.main.runner.events import EventCallback, _append_step, _emit
from app.agents.visual_summary.planning.section_diagrams import author_section_diagrams
from app.agents.visual_summary.planning.study_sheet import STUDY_SHEET_PROFILE
from app.agents.visual_summary.streaming.progressive import (
    progressive_assemble_presentation,
    should_use_progressive_render,
)
from app.agents.visual_summary.tools import (
    VISUAL_SUMMARY_AGENT_LABEL,
    run_plan_layout,
    run_render_ui,
)
from app.config import settings
from app.mcp.drawio import (
    attach_drawio_to_spec,
    enabled_mcp_ids_from_run,
    render_section_diagrams_via_mcp,
    run_drawio_mcp_for_visual,
)
from app.models import AgentRun, Document, Workspace
from app.agents.visual_summary.render.answer import resolve_presentation_answer
from app.agents.visual_summary.context import PresentationContext
from app.agents.visual_summary.handoff.evidence import (
    collect_evidence_from_steps,
    serialize_agent_evidence,
)
from app.agents.visual_summary.handoff.extract import resolve_structured_content
from app.agents.visual_summary.workspace.context import resolve_workspace_context


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
        db, run.workspace_id, user_id=run.user_id
    )
    run._workspace_context = packet  # type: ignore[attr-defined]
    structured_content, structured_source = resolve_structured_content(
        narrative,
        goal=goal,
        db=db,
        user_id=user_id,
        workspace_id=run.workspace_id,
        workspace_packet=packet,
        evidence=agent_evidence,
    )
    # Prefer main-agent streamed sections when they are richer than extract.
    streamed = getattr(run, "_streamed_sections", None)
    if not streamed and isinstance(run.run_options, dict):
        streamed = run.run_options.get("streamed_sections")
    if isinstance(streamed, list) and len(streamed) >= 2:
        clean_secs: list[dict] = []
        for s in streamed:
            if not isinstance(s, dict):
                continue
            heading = str(s.get("heading") or "").strip()
            body = str(s.get("body") or "").strip()
            bullets = s.get("bullets") if isinstance(s.get("bullets"), list) else []
            bullets = [str(b).strip() for b in bullets if str(b).strip()]
            if heading and (body or bullets):
                clean_secs.append(
                    {"heading": heading, "body": body, "bullets": bullets}
                )
        existing = structured_content.get("sections") or []
        if len(clean_secs) >= max(2, len(existing) if isinstance(existing, list) else 0):
            structured_content = dict(structured_content)
            structured_content["sections"] = clean_secs
            structured_source = f"{structured_source}+streamed"
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
        structured_source=structured_source,
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


_SECTION_TAG_RE = re.compile(r"^__section:(\d+)$")


def _panel_index_from_tags(tags: Any) -> int | None:
    for t in tags if isinstance(tags, list) else []:
        m = _SECTION_TAG_RE.match(str(t))
        if m:
            return int(m.group(1))
    return None


def _study_sheet_panel_sections(
    plan: dict[str, Any], structured: dict[str, Any] | None
) -> list[tuple[int, dict[str, Any]]]:
    """(panel_index, section_dict) pairs — panel_index matches the __section:N
    tag assemble_block already stamps on each rendered block (see
    render/assemble.py), so results key onto blocks without re-deriving order.
    """
    sections = structured.get("sections") if isinstance(structured, dict) else None
    if not isinstance(sections, list):
        return []
    out: list[tuple[int, dict[str, Any]]] = []
    for entry in plan.get("block_outline") or []:
        if not isinstance(entry, dict):
            continue
        try:
            panel_n = int(entry.get("panel_index") or entry.get("section_index") or 0)
            sec_idx = int(entry.get("section_index") or 0)
        except (TypeError, ValueError):
            continue
        if panel_n < 1 or sec_idx < 1 or sec_idx > len(sections):
            continue
        sec = sections[sec_idx - 1]
        if isinstance(sec, dict):
            out.append((panel_n, sec))
    return out


def _apply_section_diagrams_to_spec(
    spec: dict[str, Any], rendered: dict[int, dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    """Attach draw.io/MCP figure fields onto existing panels (augment, never replace).

    Teaching text (items/body/nodes) stays; optional mermaid/PNG enrich the card.
    """
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not rendered:
        return spec, 0
    applied = 0
    new_blocks: list[Any] = []
    for b in blocks:
        panel_n = _panel_index_from_tags(b.get("tags")) if isinstance(b, dict) else None
        result = rendered.get(panel_n) if panel_n is not None else None
        if not isinstance(b, dict) or result is None:
            new_blocks.append(b)
            continue
        applied += 1
        enriched = dict(b)
        # Keep original type (flow_diagram / key_points / …); only attach MCP fields.
        for key in (
            "mermaid",
            "diagram_kind",
            "edit_url",
            "preview_url",
            "png_url",
            "png_data_url",
            "png_error",
            "source",
            "mcp_error",
        ):
            if result.get(key) is not None:
                enriched[key] = result.get(key)
        new_blocks.append(enriched)
    out = dict(spec)
    out["blocks"] = new_blocks
    return out, applied


def _progressive_render_ui(
    db: Session,
    run: AgentRun,
    *,
    ctx: PresentationContext,
    plan: dict[str, Any],
    structured: dict[str, Any],
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    on_event: EventCallback = None,
) -> dict[str, Any]:
    """
    Assemble presentation panels progressively and stream each paint over SSE.

    Emits ``presentation_panel_ready`` (and a ``status`` snapshot) after each
    text/figure phase so the Visual tab can update without waiting for the
    full board. Commits partial ``presentation_spec`` for reconnect safety.
    """
    source_files: list[str] = []
    for hit in (ctx.agent_evidence.document_hits if ctx.agent_evidence else [])[:6]:
        name = getattr(hit, "filename", None) or "document"
        if name not in source_files:
            source_files.append(name)
    for name in ctx.document_filenames or []:
        if name and name not in source_files:
            source_files.append(name)

    def on_panel(payload: dict[str, Any]) -> None:
        phase = str(payload.get("phase") or "")
        spec = payload.get("presentation_spec")
        if not isinstance(spec, dict):
            return
        run.presentation_spec = spec
        try:
            db.commit()
        except Exception:
            db.rollback()
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
        )
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            presentation_spec=spec,
            final_answer=run.final_answer,
        )

    spec = progressive_assemble_presentation(
        plan,
        structured,
        goal=ctx.goal or run.goal or "",
        workspace_name=ctx.workspace_name or "",
        source_files=source_files,
        on_panel=on_panel,
    )
    blocks = spec.get("blocks") if isinstance(spec, dict) else None
    if not blocks:
        return {
            "status": "empty",
            "spec": spec,
            "block_count": 0,
            "assembly_meta": (spec or {}).get("assembly_meta")
            if isinstance(spec, dict)
            else None,
        }

    # Usage log — progressive path is code-only (0 LLM tokens).
    from app.usage import log_usage

    log_usage(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind="visual_summary_render",
        model="code_assembly_progressive",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        meta={
            "goal": (ctx.goal or "")[:200],
            "render_fallback_used": False,
            "block_count": len(blocks),
            "progressive": True,
            "plan_prevalidated": True,
        },
    )

    run.presentation_spec = spec
    try:
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "rendered",
        "spec": spec,
        "presentation_profile": spec.get("presentation_profile"),
        "block_count": len(blocks),
        "model": "code_assembly_progressive",
        "prompt": "PROGRESSIVE CODE ASSEMBLY — panels streamed text-first then figure",
        "llm_output": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "assembly_meta": spec.get("assembly_meta"),
    }


def _run_visual_pipeline(
    db: Session,
    run: AgentRun,
    *,
    ctx: PresentationContext,
    step_index: int,
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Code orchestrator for the Visual Summary phase: plan_layout → render_ui
    with no outer agent loop. Records the same tool_call/tool_result steps the
    loop would, so the execution trace and token accounting are unchanged.
    """
    user_id = run.user_id or uuid.UUID(int=0)
    initial_usage = int(run.token_usage or 0)
    prompt_total = completion_total = tokens_total = 0

    def record_tool(
        tool_name: str,
        args: dict[str, Any],
        invoke,
    ) -> tuple[dict[str, Any], Any]:
        """Run one visual tool with loop-equivalent step records and events."""
        nonlocal step_index, prompt_total, completion_total, tokens_total
        step_index += 1
        _append_step(
            db,
            run,
            step_index=step_index,
            type="tool_call",
            tool_name=tool_name,
            input=_visual_tool_call_input(tool_name, args, ctx=ctx),
            on_event=on_event,
        )
        _emit(
            on_event,
            "tool_start",
            run_id=str(run.id),
            tool_name=tool_name,
            tool_args=args,
            call_id=f"vs-{tool_name}",
        )
        t0 = time.perf_counter()
        extra: Any = None
        try:
            payload, extra = invoke()
        except Exception as e:  # surface tool failures as results, like the loop
            payload = {"error": str(e)}
        ms = (time.perf_counter() - t0) * 1000
        step_index += 1
        _append_step(
            db,
            run,
            step_index=step_index,
            type="tool_result",
            tool_name=tool_name,
            input=_visual_tool_result_input(tool_name, args, payload),
            output=payload,
            on_event=on_event,
            duration_ms=round(ms, 1),
        )
        prompt_total, completion_total, tokens_total = _accumulate_visual_tool_tokens(
            payload,
            prompt_tokens_total=prompt_total,
            completion_tokens_total=completion_total,
            total_tokens_acc=tokens_total,
        )
        return payload, extra

    plan_payload, plan_result = record_tool(
        "plan_layout",
        {"notes": ""},
        lambda: run_plan_layout(
            db,
            ctx,
            user_id=user_id,
            workspace_id=run.workspace_id,
        ),
    )

    plan = (plan_result or {}).get("plan") if isinstance(plan_result, dict) else None
    structured: dict[str, Any] | None = None
    if isinstance(plan, dict) and plan:
        # Let the UI show placeholder blocks while render runs.
        _emit(
            on_event,
            "presentation_skeleton",
            run_id=str(run.id),
            presentation_profile=plan.get("presentation_profile"),
            outline=[
                {
                    "type": str(entry.get("type")),
                    "title": str(entry.get("title") or ""),
                    "width": entry.get("width") or None,
                }
                for entry in (plan.get("block_outline") or [])
                if isinstance(entry, dict) and entry.get("type")
            ],
        )
        # Plan was already validated (with repair + skeleton fallback) inside
        # run_plan_layout — render without re-validating (validate-once).
        validated = plan_payload.get("validation_status") == "passed"
        structured = plan_result.get("structured_content")
        structured_dict = structured if isinstance(structured, dict) else None

        # Progressive path: assemble panels one-by-one (text-first, then figure)
        # so the Visual tab can paint before the full board is ready.
        if should_use_progressive_render(plan) and structured_dict is not None:
            render_payload, _ = record_tool(
                "render_ui",
                {"layout_plan_json": "{}", "mode": "progressive"},
                lambda: (
                    _progressive_render_ui(
                        db,
                        run,
                        ctx=ctx,
                        plan=plan,
                        structured=structured_dict,
                        user_id=user_id,
                        workspace_id=run.workspace_id,
                        on_event=on_event,
                    ),
                    None,
                ),
            )
            # Empty progressive → fall back to batch code/LLM render.
            if (
                isinstance(render_payload, dict)
                and render_payload.get("status") == "empty"
            ):
                render_payload, _ = record_tool(
                    "render_ui",
                    {"layout_plan_json": "{}", "mode": "batch_fallback"},
                    lambda: (
                        run_render_ui(
                            db,
                            ctx,
                            plan=plan,
                            user_id=user_id,
                            workspace_id=run.workspace_id,
                            structured=structured_dict,
                            validated=validated,
                        ),
                        None,
                    ),
                )
        else:
            render_payload, _ = record_tool(
                "render_ui",
                {"layout_plan_json": "{}"},
                lambda: (
                    run_render_ui(
                        db,
                        ctx,
                        plan=plan,
                        user_id=user_id,
                        workspace_id=run.workspace_id,
                        structured=structured_dict,
                        validated=validated,
                    ),
                    None,
                ),
            )
        _apply_render_ui_result(
            run,
            tool_name="render_ui",
            result=render_payload,
            on_event=on_event,
        )

    # Optional draw.io MCP — always attempt when enabled, even if plan/render failed.
    mcp_ids = enabled_mcp_ids_from_run(run)
    section_diagrams_applied = False
    if (
        "mcp_drawio" in mcp_ids
        and isinstance(plan, dict)
        and plan.get("presentation_profile") == STUDY_SHEET_PROFILE
        and isinstance(run.presentation_spec, dict)
    ):
        panel_sections = _study_sheet_panel_sections(
            plan, structured if isinstance(structured, dict) else None
        )
        max_sections = int(getattr(settings, "mcp_drawio_max_sections", 8) or 8)
        panel_sections = panel_sections[:max_sections]

        def _run_section_diagrams() -> tuple[dict[str, Any], None]:
            authored = author_section_diagrams(
                panel_sections,
                goal=ctx.goal or run.goal or "",
                db=db,
                user_id=user_id,
                workspace_id=run.workspace_id,
            )
            if not authored:
                return {"status": "skipped", "reason": "no_sections_need_diagram"}, None
            sections_mermaid = {
                idx: (data["mermaid"], data["diagram_kind"])
                for idx, data in authored.items()
            }
            rendered = render_section_diagrams_via_mcp(sections_mermaid)
            new_spec, applied = _apply_section_diagrams_to_spec(
                run.presentation_spec, rendered
            )
            run.presentation_spec = new_spec
            return {
                "status": "ok",
                "sections_authored": len(authored),
                "sections_applied": applied,
            }, None

        section_diagrams_payload, _ = record_tool(
            "mcp_drawio_sections",
            {
                "connector_id": "mcp_drawio",
                "presentation_profile": STUDY_SHEET_PROFILE,
                "candidate_sections": len(panel_sections),
            },
            _run_section_diagrams,
        )
        if isinstance(section_diagrams_payload, dict):
            section_diagrams_applied = bool(section_diagrams_payload.get("sections_applied"))
            _emit(
                on_event,
                "presentation",
                run_id=str(run.id),
                presentation_spec=run.presentation_spec,
            )

    # Skip the single whole-run diagram once per-section diagrams already
    # replaced the relevant blocks — avoids showing both for the same run.
    if section_diagrams_applied:
        mcp_ids = [m for m in mcp_ids if m != "mcp_drawio"]
    if "mcp_drawio" in mcp_ids:
        structured_for_mcp = (
            ctx.structured_content
            if isinstance(ctx.structured_content, dict)
            else {}
        )
        drawio_payload, _ = record_tool(
            "mcp_drawio",
            {
                "connector_id": "mcp_drawio",
                "goal": (ctx.goal or run.goal or "")[:200],
            },
            lambda: (
                run_drawio_mcp_for_visual(
                    structured=structured_for_mcp,
                    goal=ctx.goal or run.goal or "",
                    presentation_spec=run.presentation_spec
                    if isinstance(run.presentation_spec, dict)
                    else None,
                ),
                None,
            ),
        )
        if isinstance(drawio_payload, dict):
            if not isinstance(run.presentation_spec, dict):
                # Ensure Visual tab can still show the draw.io export card.
                run.presentation_spec = {
                    "type": "generative_ui",
                    "title": (run.goal or "Visual summary")[:80],
                    "plain_summary": (run.final_answer or "")[:500],
                    "blocks": [],
                }
            run.presentation_spec = attach_drawio_to_spec(
                run.presentation_spec,
                drawio_payload,
            )
            _emit(
                on_event,
                "presentation",
                run_id=str(run.id),
                presentation_spec=run.presentation_spec,
            )
            _emit(
                on_event,
                "status",
                run_id=str(run.id),
                status=run.status,
                presentation_spec=run.presentation_spec,
                final_answer=run.final_answer,
            )

    run.status = "completed"
    run.token_usage = (initial_usage + tokens_total) or None
    run.pending_tool = None
    _finalize_visual_summary_run(
        db,
        run,
        step_index=step_index,
        on_event=on_event,
    )
    from app.agents.main.storage.run_storage import compact_run_if_terminal

    compact_run_if_terminal(db, run)
    db.commit()
    db.refresh(run)
    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status=run.status,
        token_usage=run.token_usage,
        pending_tool=run.pending_tool,
        final_answer=run.final_answer,
    )
    return run


def _maybe_apply_drawio_mcp(
    db: Session,
    run: AgentRun,
    *,
    ctx: PresentationContext,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """If the user enabled draw.io MCP, attach export URL + tool steps."""
    if "mcp_drawio" not in enabled_mcp_ids_from_run(run):
        return step_index
    if not isinstance(run.presentation_spec, dict):
        return step_index
    # Skip if already applied (orchestrator path records the tool once).
    meta = run.presentation_spec.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("drawio"), dict):
        if meta["drawio"].get("edit_url") or meta["drawio"].get("status") == "skipped":
            return step_index

    structured = (
        ctx.structured_content if isinstance(ctx.structured_content, dict) else {}
    )
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_call",
        tool_name="mcp_drawio",
        input={"connector_id": "mcp_drawio", "goal": (ctx.goal or "")[:200]},
        on_event=on_event,
    )
    payload = run_drawio_mcp_for_visual(
        structured=structured,
        goal=ctx.goal or run.goal or "",
        presentation_spec=run.presentation_spec
        if isinstance(run.presentation_spec, dict)
        else None,
    )
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_result",
        tool_name="mcp_drawio",
        input={"connector_id": "mcp_drawio"},
        output=payload,
        on_event=on_event,
    )
    run.presentation_spec = attach_drawio_to_spec(run.presentation_spec, payload)
    _emit(
        on_event,
        "presentation",
        run_id=str(run.id),
        presentation_spec=run.presentation_spec,
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

    ctx = _presentation_context_for_run(db, run)
    # Agent-loop path may not have run draw.io yet.
    step_index = _maybe_apply_drawio_mcp(
        db, run, ctx=ctx, step_index=step_index, on_event=on_event
    )
    spec = run.presentation_spec if isinstance(run.presentation_spec, dict) else spec

    if _has_presentation_step(run):
        return step_index

    return _attach_presentation_step(
        db,
        run,
        spec=spec,
        step_index=step_index,
        agent_evidence=ctx.agent_evidence,
        on_event=on_event,
    )
