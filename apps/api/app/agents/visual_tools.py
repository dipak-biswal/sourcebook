"""Tools for the Visual Summary Agent (layout planning + UI rendering)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.tools import tool
from openai import OpenAI
from sqlalchemy.orm import Session

from app.agents.date_tools import get_current_date
from app.config import settings
from app.presentation.context import PresentationContext
from app.presentation.engine import build_presentation
from app.presentation.handoff import (
    _format_evidence_block,
    combined_extract_plan_enabled,
    format_combined_extract_plan_prompt,
    normalize_structured_content,
    structured_content_has_substance,
)
from app.presentation.layout import format_layout_requirements, layout_components_from_goal
from app.presentation.llm_json import (
    COMBINED_EXTRACT_PLAN_SCHEMA,
    PLAN_SCHEMA,
    chat_json,
)
from app.presentation.layout_stabilize import (
    stabilize_layout_plan,
    stabilize_process_flow_topology,
)
from app.presentation.plan_validator import format_validator_notes, validate_layout_plan
from app.presentation.structured import (
    build_plan_layout_input,
    extract_structured_content,
    format_plan_layout_prompt,
)
from app.presentation.interactions import interaction_boosts_for_workspace
from app.presentation.ui_intent import (
    available_source_hints,
    build_skeleton_layout_plan,
    resolve_ui_intent,
)
from app.usage import estimate_tokens, log_usage

VISUAL_SUMMARY_AGENT_LABEL = "Visual Summary Agent"
_MAX_AUTO_REPLANS = 1


def _client() -> OpenAI:
    # Explicit bounds — see app/agents/runner/llm.py for why.
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=60.0,
        max_retries=2,
    )


def _merge_usage(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    prompt = int(a.get("prompt_tokens") or 0) + int(b.get("prompt_tokens") or 0)
    completion = int(a.get("completion_tokens") or 0) + int(b.get("completion_tokens") or 0)
    total = int(a.get("total_tokens") or 0) + int(b.get("total_tokens") or 0)
    if total <= 0 and (prompt > 0 or completion > 0):
        total = prompt + completion
    return {
        "model": b.get("model") or a.get("model"),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _packet_and_hints(ctx: PresentationContext) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    packet = ctx.workspace_packet if isinstance(ctx.workspace_packet, dict) else None
    hints = None
    if packet and isinstance(packet.get("derived"), dict):
        derived = packet["derived"]
        hints = {
            "suggested_affordances": list(derived.get("visual_affordances") or []),
            "emphasis": str(
                derived.get("success_criteria") or derived.get("outcome_phrase") or ""
            ),
        }
    return packet, hints


def _ensure_structured(ctx: PresentationContext) -> dict[str, Any]:
    """Resolve structured content once and pin it on the context.

    The orchestrator / handoff already populates ctx.structured_content. Downstream
    plan/render paths must reuse that value so heuristic extraction does not re-run
    with different inputs mid-pipeline. Only extract when the field is still empty
    (standalone tool calls / tests).
    """
    if isinstance(ctx.structured_content, dict) and ctx.structured_content:
        structured = normalize_structured_content(ctx.structured_content)
        ctx.structured_content = structured
        return structured
    goal = (ctx.goal or "").strip()
    structured = normalize_structured_content(
        extract_structured_content(ctx.final_answer or "", goal=goal)
    )
    ctx.structured_content = structured
    if not ctx.structured_source:
        ctx.structured_source = "heuristic"
    return structured


def _plan_layout_skeleton(ctx: PresentationContext) -> dict[str, Any]:
    """Code-first layout from UiIntent (affordance ∩ data)."""
    goal = (ctx.goal or "").strip()
    structured = _ensure_structured(ctx)
    packet, hints = _packet_and_hints(ctx)
    intent = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        presentation_hints=hints,
        goal=goal,
        interaction_boosts=ctx.interaction_boosts,
    )
    plan = build_skeleton_layout_plan(intent, structured_content=structured)
    components = list(plan.get("components") or [])
    planner_input = build_plan_layout_input(
        goal=goal,
        structured_content=structured,
        evidence=ctx.agent_evidence,
        components=components,
        notes="code_skeleton",
    )
    return {
        "plan": plan,
        "structured_input": planner_input,
        "prompt": (
            "CODE SKELETON PLAN (no LLM)\n"
            f"UiIntent block_order: {intent.block_order}\n"
            f"Eligible: {intent.eligible_affordances}\n"
            f"Emphasis: {intent.emphasis}"
        ),
        "llm_output": json.dumps(plan, ensure_ascii=False),
        "usage": {
            "model": "code_skeleton",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "structured_content": structured,
        "requested_components": components,
        "ui_intent": intent.to_dict(),
    }


def _plan_layout_llm(
    ctx: PresentationContext,
    *,
    notes: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    skeleton: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal = (ctx.goal or "").strip()
    # Skeleton provides a reference outline + component list; LLM may reorder/select.
    # It also carries the structured content, resolved exactly once per plan.
    if skeleton is None:
        skeleton = _plan_layout_skeleton(ctx)
    structured = skeleton["structured_content"]
    components = list(skeleton["plan"].get("components") or layout_components_from_goal(goal))
    layout_hints = format_layout_requirements(components)
    present_fields = sorted(available_source_hints(structured))
    planner_input = build_plan_layout_input(
        goal=goal,
        structured_content=structured,
        evidence=ctx.agent_evidence,
        components=components,
        notes=notes,
        available_fields=present_fields,
    )
    packet, _hints = _packet_and_hints(ctx)
    workspace_example = None
    if packet and isinstance(packet.get("derived"), dict):
        candidate = packet["derived"].get("planner_example")
        if isinstance(candidate, dict):
            workspace_example = candidate
    prompt = format_plan_layout_prompt(
        planner_input,
        layout_hints=layout_hints,
        workspace_example=workspace_example,
    )
    # Reference outline — not a cage. LLM chooses order, titles, width, subset.
    prompt = (
        f"{prompt}\n\n"
        "REFERENCE SKELETON OUTLINE (optional starting point — you may reorder, "
        "retitle, change width, or select a different subset of available source_hints; "
        "do not invent empty blocks without data):\n"
        f"{json.dumps(skeleton['plan'].get('block_outline') or [], ensure_ascii=False)}\n"
    )

    resp = chat_json(
        _client(),
        model=settings.visual_summary_model,
        system=(
            "You are the Visual Summary layout planner. Output valid JSON only. "
            "Decide which blocks to show, their order, titles, source_hint, and width. "
            "Use only available source_hint fields from the prompt. Do not invent facts. "
            "presentation_profile must be a real short snake_case id for this layout "
            "(e.g. mechanism_explainer, gap_analysis) — never the placeholder short_snake_case."
        ),
        prompt=prompt,
        schema_name="layout_plan",
        schema=PLAN_SCHEMA,
        temperature=0.0,
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        plan = dict(skeleton["plan"])
        plan["rationale"] = "Fallback to code skeleton — model returned invalid JSON."

    if not isinstance(plan, dict):
        plan = {}
    # If LLM emptied outline, fall back to skeleton
    if not plan.get("block_outline"):
        plan = dict(skeleton["plan"])
    plan.setdefault("components", components)
    plan.setdefault("presentation_profile", "workspace_derived")
    plan.setdefault("block_outline", [])
    plan.setdefault("rationale", "")
    if "ui_intent" not in plan:
        plan["ui_intent"] = skeleton.get("ui_intent")

    usage = getattr(resp, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(raw)

    usage_payload = {
        "model": settings.visual_summary_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

    if db is not None and user_id is not None and workspace_id is not None:
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_plan",
            model=usage_payload["model"],
            prompt_tokens=int(usage_payload["prompt_tokens"] or 0),
            completion_tokens=int(usage_payload["completion_tokens"] or 0),
            total_tokens=int(usage_payload["total_tokens"] or 0),
            meta={"goal": goal[:200], "replan": bool(notes.strip())},
        )

    return {
        "plan": plan,
        "structured_input": planner_input,
        "prompt": prompt,
        "llm_output": raw,
        "usage": usage_payload,
        "structured_content": structured,
        "requested_components": components,
        "ui_intent": skeleton.get("ui_intent"),
    }


def _workspace_block_from_packet_dict(packet: dict[str, Any] | None) -> str:
    """Compact workspace signal for the combined prompt (dict-form packet)."""
    if not isinstance(packet, dict):
        return ""
    identity = packet.get("identity") if isinstance(packet.get("identity"), dict) else {}
    derived = packet.get("derived") if isinstance(packet.get("derived"), dict) else {}
    if not identity and not derived:
        return ""
    affs = derived.get("visual_affordances") or []
    return (
        f"Workspace: {identity.get('name') or '(unnamed)'}\n"
        f"Description: {str(identity.get('description') or '')[:400] or '(none)'}\n"
        f"Outcome: {derived.get('outcome_phrase') or ''}\n"
        f"Tone: {derived.get('tone') or ''}\n"
        f"Success: {derived.get('success_criteria') or ''}\n"
        f"Suggested affordances: {', '.join(str(a) for a in affs[:10])}"
    )


def _extract_and_plan_llm(
    ctx: PresentationContext,
    *,
    skeleton: dict[str, Any],
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """
    ONE LLM call that extracts structured content AND plans the layout.

    Replaces the separate extraction + planning calls on the happy path.
    Returns a result shaped like _plan_layout_llm's (plus structured_content
    from its own extraction), or None so the caller falls back to two calls.
    """
    goal = (ctx.goal or "").strip()
    answer = (ctx.final_answer or "").strip()
    if len(answer) < 40:
        return None

    components = list(skeleton["plan"].get("components") or [])
    prompt = format_combined_extract_plan_prompt(
        answer,
        goal=goal,
        workspace_block=_workspace_block_from_packet_dict(ctx.workspace_packet),
        evidence_block=_format_evidence_block(ctx.agent_evidence),
        layout_hints=format_layout_requirements(components),
        skeleton_outline=json.dumps(
            skeleton["plan"].get("block_outline") or [], ensure_ascii=False
        ),
    )
    try:
        resp = chat_json(
            _client(),
            model=settings.visual_summary_model,
            system=(
                "You extract structured facts from an agent answer and plan a "
                "visual layout from them, in one JSON response. Never invent facts. "
                "presentation_profile must be a real short snake_case id "
                "(e.g. mechanism_explainer) — never the placeholder short_snake_case. "
                "For explain/how-it-works goals: process_flow must be a linear handoff "
                "chain of concrete components (not a star with an abstract hub node); "
                "also fill interaction_sequence with one concrete worked example."
            ),
            prompt=prompt,
            schema_name="extract_and_plan",
            schema=COMBINED_EXTRACT_PLAN_SCHEMA,
            temperature=0.0,
        )
    except Exception:
        return None

    raw = (resp.choices[0].message.content or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    structured = normalize_structured_content(parsed.get("structured_content"))
    structured = stabilize_process_flow_topology(structured)
    plan = parsed.get("layout_plan")
    if not isinstance(plan, dict) or not structured_content_has_substance(structured):
        return None
    plan.setdefault("presentation_profile", "workspace_derived")
    plan.setdefault("components", components)
    plan.setdefault("block_outline", [])
    plan.setdefault("rationale", "")
    plan = stabilize_layout_plan(
        plan,
        structured=structured,
        skeleton_plan=skeleton.get("plan") if isinstance(skeleton, dict) else None,
        goal=goal,
    )

    usage = getattr(resp, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(raw)
    usage_payload = {
        "model": settings.visual_summary_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if db is not None and user_id is not None and workspace_id is not None:
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_extract_plan",
            model=usage_payload["model"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=usage_payload["total_tokens"],
            meta={"goal": goal[:200]},
        )

    return {
        "plan": plan,
        "prompt": prompt,
        "llm_output": raw,
        "usage": usage_payload,
        "structured_content": structured,
        "requested_components": list(plan.get("components") or components),
    }


def _outline_empty_or_ungrounded(
    plan: dict[str, Any],
    structured: dict[str, Any],
) -> bool:
    """True when the plan has no usable grounded outline entries."""
    outline = plan.get("block_outline") or []
    if not outline:
        return True
    present = available_source_hints(structured)
    grounded = 0
    for entry in outline:
        if not isinstance(entry, dict):
            continue
        hint = str(entry.get("source_hint") or "").strip()
        if hint and hint in present:
            grounded += 1
        elif not hint and entry.get("type"):
            # Legacy entry without source_hint — treat as potentially usable
            grounded += 1
    return grounded == 0


def _plan_with_validation(
    ctx: PresentationContext,
    *,
    notes: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Layout planning with grounding validation.

    Default: ONE combined extract+plan LLM call (when the context still holds
    the heuristic extraction); repair is the only extra call. With the
    combined flag off, the planner LLM runs against pre-extracted structured
    content. With visual_summary_llm_planner off: skeleton-first (legacy).
    """
    # Load interaction boosts once per plan (chip/FAQ signals from prior runs).
    if (
        db is not None
        and user_id is not None
        and workspace_id is not None
        and ctx.interaction_boosts is None
    ):
        try:
            ctx.interaction_boosts = interaction_boosts_for_workspace(
                db, user_id=user_id, workspace_id=workspace_id
            ) or None
        except Exception:
            ctx.interaction_boosts = None
    skeleton_result = _plan_layout_skeleton(ctx)
    structured = skeleton_result["structured_content"]
    llm_primary = bool(getattr(settings, "visual_summary_llm_planner", True))

    # --- Combined extract+plan: one LLM call instead of extract then plan ---
    # Only on the first pass (no notes) and only when the context still holds
    # the heuristic extraction — an "llm" source means extraction already ran.
    if (
        llm_primary
        and not notes.strip()
        and ctx.structured_source == "heuristic"
        and combined_extract_plan_enabled()
    ):
        combined = _extract_and_plan_llm(
            ctx,
            skeleton=skeleton_result,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if combined is not None:
            # Re-anchor the context and skeleton on the richer combined
            # extraction so validation, repair, and fallback are grounded in it.
            ctx.structured_content = combined["structured_content"]
            ctx.structured_source = "llm"
            new_skeleton = _plan_layout_skeleton(ctx)
            combined["ui_intent"] = new_skeleton.get("ui_intent")
            combined["structured_input"] = build_plan_layout_input(
                goal=ctx.goal or "",
                structured_content=combined["structured_content"],
                evidence=ctx.agent_evidence,
                components=list(combined.get("requested_components") or []),
                notes="combined_extract_plan",
            )
            return _plan_llm_with_repair_and_fallback(
                ctx,
                skeleton_result=new_skeleton,
                notes="",
                db=db,
                user_id=user_id,
                workspace_id=workspace_id,
                first_attempt=combined,
                first_source="combined",
            )

    # --- Legacy skeleton-first path (flag off, no notes) ---
    if not llm_primary and not notes.strip():
        plan = skeleton_result["plan"]
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        if ok:
            return {
                **skeleton_result,
                "validation_status": "passed",
                "validation_errors": [],
                "replan_attempted": False,
                "planner_source": "skeleton",
            }
        # Skeleton invalid → LLM repair, then skeleton fallback if still bad
        return _plan_llm_with_repair_and_fallback(
            ctx,
            skeleton_result=skeleton_result,
            notes=format_validator_notes(errors) if errors else "",
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    # --- LLM primary (or notes-driven call when flag off) ---
    return _plan_llm_with_repair_and_fallback(
        ctx,
        skeleton_result=skeleton_result,
        notes=notes.strip(),
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
    )


def _plan_llm_with_repair_and_fallback(
    ctx: PresentationContext,
    *,
    skeleton_result: dict[str, Any],
    notes: str,
    db: Session | None,
    user_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    first_attempt: dict[str, Any] | None = None,
    first_source: str = "llm",
) -> dict[str, Any]:
    """
    Validate the first plan attempt, optional one repair pass, then skeleton
    fallback. The first attempt is either the plan-only LLM call (default) or
    a precomputed combined extract+plan result (first_attempt).
    """
    structured = skeleton_result["structured_content"]
    replan_attempted = False
    replan_prompt = ""
    replan_llm_output = ""
    merged_usage = dict(skeleton_result["usage"])

    llm = first_attempt if first_attempt is not None else _plan_layout_llm(
        ctx,
        notes=notes,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        skeleton=skeleton_result,
    )
    merged_usage = _merge_usage(merged_usage, llm["usage"])
    plan = llm["plan"]
    structured = llm.get("structured_content") or structured
    structured = stabilize_process_flow_topology(structured)
    plan = stabilize_layout_plan(
        plan,
        structured=structured,
        skeleton_plan=skeleton_result.get("plan"),
        goal=ctx.goal or "",
    )
    ok, errors = validate_layout_plan(
        plan,
        goal=ctx.goal or "",
        structured_content=structured,
        requested_components=[],
        final_answer=ctx.final_answer or "",
    )
    result = {
        **skeleton_result,
        **llm,
        "plan": plan,
        "structured_content": structured,
    }
    planner_source = first_source

    # One repair pass when validation fails
    if not ok and _MAX_AUTO_REPLANS > 0:
        repair_notes = format_validator_notes(errors)
        if notes.strip():
            repair_notes = f"{notes.strip()}\n\n{repair_notes}"
        second = _plan_layout_llm(
            ctx,
            notes=repair_notes,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
            skeleton=skeleton_result,
        )
        replan_attempted = True
        replan_prompt = second["prompt"]
        replan_llm_output = second["llm_output"]
        merged_usage = _merge_usage(merged_usage, second["usage"])
        plan = second["plan"]
        structured = stabilize_process_flow_topology(
            second.get("structured_content") or structured
        )
        plan = stabilize_layout_plan(
            plan,
            structured=structured,
            skeleton_plan=skeleton_result.get("plan"),
            goal=ctx.goal or "",
        )
        planner_source = "llm"
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        result = {
            **result,
            **second,
            "plan": plan,
            "structured_content": structured,
        }

    # Fallback: invalid plan, empty outline, or fully ungrounded
    if (
        not ok
        or _outline_empty_or_ungrounded(plan, structured)
    ):
        planner_source = "skeleton"
        # Rebuild skeleton against the latest structured (may include combined extract)
        intent = resolve_ui_intent(
            structured_content=structured,
            workspace_packet=ctx.workspace_packet,
            goal=ctx.goal or "",
            interaction_boosts=ctx.interaction_boosts,
        )
        sk_plan = build_skeleton_layout_plan(intent, structured_content=structured)
        plan = stabilize_layout_plan(
            sk_plan,
            structured=structured,
            skeleton_plan=sk_plan,
            goal=ctx.goal or "",
        )
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        result = {
            **result,
            **skeleton_result,
            "plan": plan,
            "structured_content": structured,
            "ui_intent": intent.to_dict(),
            # Keep LLM prompt/output for the trace when primary path ran
            "prompt": result.get("prompt") or skeleton_result.get("prompt"),
            "llm_output": result.get("llm_output") or skeleton_result.get("llm_output"),
            "structured_input": result.get("structured_input")
            or skeleton_result.get("structured_input"),
        }

    # Final stabilize pass (profile + diagram injection) even when validation passed
    plan = stabilize_layout_plan(
        plan,
        structured=structured,
        skeleton_plan=skeleton_result.get("plan"),
        goal=ctx.goal or "",
    )
    structured = stabilize_process_flow_topology(structured)

    status = "passed" if ok else "failed"
    return {
        **result,
        "plan": plan,
        "structured_content": structured,
        "usage": merged_usage,
        "validation_status": status,
        "validation_errors": errors if not ok else (errors or []),
        "replan_attempted": replan_attempted,
        "replan_prompt": replan_prompt or None,
        "replan_llm_output": replan_llm_output or None,
        "planner_source": planner_source,
    }


def run_plan_layout(
    db: Session | None,
    ctx: PresentationContext,
    *,
    notes: str = "",
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Produce a validated layout plan for the handoff context.

    Returns (payload, result): payload is the tool-facing dict recorded on the
    trace; result is the internal _plan_with_validation output (validated plan
    + structured content) for callers that render next without re-validating.
    """
    result = _plan_with_validation(
        ctx,
        notes=notes,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    usage = result["usage"]
    payload: dict[str, Any] = {
        "status": "planned" if result["validation_status"] == "passed" else "validation_failed",
        "layout_plan": result["plan"],
        "structured_input": result.get("structured_input"),
        "ui_intent": result.get("ui_intent") or (result.get("plan") or {}).get("ui_intent"),
        "validation_status": result["validation_status"],
        "validation_errors": result.get("validation_errors") or [],
        "replan_attempted": result.get("replan_attempted", False),
        "model": usage["model"],
        "prompt": result["prompt"],
        "llm_output": result["llm_output"],
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
    }
    if result.get("replan_prompt"):
        payload["replan_prompt"] = result["replan_prompt"]
    if result.get("replan_llm_output"):
        payload["replan_llm_output"] = result["replan_llm_output"]
    payload["planner_source"] = result.get("planner_source") or "llm"

    # Zero-token outcome row: how planning went, regardless of which LLM
    # calls were made. Aggregated by /usage/visual-summary.
    if db is not None and workspace_id is not None:
        outline = (result.get("plan") or {}).get("block_outline") or []
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_plan_outcome",
            model=usage.get("model"),
            meta={
                "goal": (ctx.goal or "")[:200],
                "validation_status": result["validation_status"],
                "replan_attempted": bool(result.get("replan_attempted")),
                "planner_source": payload["planner_source"],
                "outline_blocks": len(outline),
            },
        )
    return payload, result


def run_render_ui(
    db: Session,
    ctx: PresentationContext,
    *,
    plan: dict[str, Any],
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    structured: dict[str, Any] | None = None,
    validated: bool = False,
) -> dict[str, Any]:
    """
    Build the generative UI spec from a layout plan.

    validated=True skips re-validation — for plans that already passed
    validate_layout_plan inside run_plan_layout (the plan/render contract is
    validate-once). Externally supplied plans must be validated here.
    """
    if structured is None:
        structured = _ensure_structured(ctx)
    else:
        structured = normalize_structured_content(structured)
        ctx.structured_content = structured
    if not validated:
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        if not ok:
            return {
                "error": "Layout plan failed validation",
                "validation_errors": errors,
            }

    render_ctx = PresentationContext(
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        goal=ctx.goal,
        final_answer=ctx.final_answer,
        workspace_name=ctx.workspace_name,
        workspace_description=ctx.workspace_description,
        workspace_tags=list(ctx.workspace_tags),
        document_filenames=list(ctx.document_filenames),
        agent_evidence=ctx.agent_evidence,
        structured_content=structured,
        layout_plan=plan,
        workspace_packet=ctx.workspace_packet,
    )
    spec, meta = build_presentation(db, render_ctx)
    if isinstance(spec, dict) and spec.get("error"):
        return {"error": spec.get("error"), "meta": meta}

    # Always log the render — the zero-token code-assembly path is the primary
    # path and was previously invisible in usage. Quality signals ride in meta.
    assembly_meta = meta.get("assembly_meta") or (
        spec.get("assembly_meta") if isinstance(spec, dict) else None
    )
    assembly_meta = assembly_meta if isinstance(assembly_meta, dict) else {}
    log_usage(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind="visual_summary_render",
        model=meta.get("model") or settings.visual_summary_model,
        prompt_tokens=int(meta.get("prompt_tokens") or 0),
        completion_tokens=int(meta.get("completion_tokens") or 0),
        total_tokens=int(meta.get("total_tokens") or 0),
        meta={
            "goal": (ctx.goal or "")[:200],
            "render_fallback_used": bool(assembly_meta.get("render_fallback_used")),
            "block_count": len(spec.get("blocks") or []) if isinstance(spec, dict) else 0,
            "assembled_blocks": len(assembly_meta.get("assembled_blocks") or []),
            "dropped_blocks": len(assembly_meta.get("dropped_blocks") or []),
            "plan_prevalidated": bool(validated),
        },
    )

    return {
        "status": "rendered",
        "spec": spec,
        "presentation_profile": spec.get("presentation_profile") if isinstance(spec, dict) else None,
        "block_count": len(spec.get("blocks") or []) if isinstance(spec, dict) else 0,
        "model": meta.get("model"),
        "prompt": meta.get("prompt"),
        "llm_output": meta.get("llm_output"),
        "prompt_tokens": meta.get("prompt_tokens"),
        "completion_tokens": meta.get("completion_tokens"),
        "total_tokens": meta.get("total_tokens"),
        "assembly_meta": meta.get("assembly_meta") or (
            spec.get("assembly_meta") if isinstance(spec, dict) else None
        ),
    }


def build_visual_tools(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: PresentationContext,
):
    """Return Visual Summary Agent tools bound to this run's handoff context."""

    # Cache the plan_layout result so render_ui can recover when the model
    # hands back malformed/truncated layout_plan_json — LLMs routinely
    # mis-serialize a multi-KB plan into tool-call arguments. The cache also
    # carries the resolved structured content and validation status so
    # render_ui neither re-extracts nor re-validates an approved plan.
    plan_cache: dict[str, Any] = {}

    @tool
    def plan_layout(notes: str = "") -> dict[str, Any]:
        """
        Analyze the handoff (goal, main agent answer, evidence) and produce a
        structured layout plan before rendering UI. Call this before render_ui.
        """
        payload, result = run_plan_layout(
            db,
            ctx,
            notes=notes,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if isinstance(result.get("plan"), dict) and result["plan"]:
            plan_cache["plan"] = result["plan"]
            plan_cache["structured"] = result.get("structured_content")
            plan_cache["validated"] = result.get("validation_status") == "passed"
        return payload

    @tool
    def render_ui(layout_plan_json: str = "") -> dict[str, Any]:
        """
        Build generative UI blocks from the approved layout plan.

        Pass "{}" to render the plan produced by plan_layout — you do not need
        to echo the full plan back. If you do pass layout_plan_json and it is
        valid, it is used; otherwise the approved plan is used automatically.
        """
        plan: dict[str, Any] | None = None
        raw = (layout_plan_json or "").strip()
        parse_error: str | None = None
        if raw and raw not in ("{}", "null"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                parse_error = f"Invalid layout_plan_json: {e}"
            else:
                if isinstance(parsed, dict) and parsed:
                    plan = parsed
                else:
                    parse_error = "layout_plan must be a JSON object"

        # Recover from a missing/malformed arg using the cached plan_layout result.
        if plan is None:
            cached = plan_cache.get("plan")
            if isinstance(cached, dict) and cached:
                plan = cached

        if plan is None:
            return {
                "error": parse_error
                or "layout_plan is required — call plan_layout before render_ui"
            }

        # Validate once: a plan that already passed inside plan_layout (used
        # from cache or echoed back verbatim) is not re-validated here.
        validated = bool(plan_cache.get("validated")) and plan == plan_cache.get("plan")
        structured = plan_cache.get("structured") if plan == plan_cache.get("plan") else None
        return run_render_ui(
            db,
            ctx,
            plan=plan,
            user_id=user_id,
            workspace_id=workspace_id,
            structured=structured if isinstance(structured, dict) else None,
            validated=validated,
        )

    return [get_current_date, plan_layout, render_ui]