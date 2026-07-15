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
from app.presentation.handoff import normalize_structured_content
from app.presentation.layout import format_layout_requirements, layout_components_from_goal
from app.presentation.plan_validator import format_validator_notes, validate_layout_plan
from app.presentation.structured import (
    build_plan_layout_input,
    extract_structured_content,
    format_plan_layout_prompt,
)
from app.presentation.ui_intent import build_skeleton_layout_plan, resolve_ui_intent
from app.usage import estimate_tokens, log_usage

VISUAL_SUMMARY_AGENT_LABEL = "Visual Summary Agent"
_MAX_AUTO_REPLANS = 1


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


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


def _plan_layout_skeleton(ctx: PresentationContext) -> dict[str, Any]:
    """Code-first layout from UiIntent (affordance ∩ data)."""
    goal = (ctx.goal or "").strip()
    structured = normalize_structured_content(
        ctx.structured_content
        or extract_structured_content(ctx.final_answer or "", goal=goal)
    )
    packet, hints = _packet_and_hints(ctx)
    intent = resolve_ui_intent(
        structured_content=structured,
        workspace_packet=packet,
        presentation_hints=hints,
        goal=goal,
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
) -> dict[str, Any]:
    goal = (ctx.goal or "").strip()
    structured = normalize_structured_content(
        ctx.structured_content
        or extract_structured_content(ctx.final_answer or "", goal=goal)
    )
    # Prefer skeleton types as the component list so LLM does not invent resume dashboards
    skeleton = _plan_layout_skeleton(ctx)
    components = list(skeleton["plan"].get("components") or layout_components_from_goal(goal))
    layout_hints = format_layout_requirements(components)
    planner_input = build_plan_layout_input(
        goal=goal,
        structured_content=structured,
        evidence=ctx.agent_evidence,
        components=components,
        notes=notes,
    )
    prompt = format_plan_layout_prompt(planner_input, layout_hints=layout_hints)
    # Anchor on skeleton — titles may improve, types should stay close
    prompt = (
        f"{prompt}\n\n"
        "SKELETON OUTLINE (prefer these types and source_hint values; "
        "do not invent empty table/progress blocks without data):\n"
        f"{json.dumps(skeleton['plan'].get('block_outline') or [], ensure_ascii=False)}\n"
    )

    client = _client()
    resp = client.chat.completions.create(
        model=settings.visual_summary_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You refine visual summary layouts. Output valid JSON only. "
                    "Prefer the provided skeleton block types; do not add resume-only profiles."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
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


def _plan_with_validation(
    ctx: PresentationContext,
    *,
    notes: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Prefer code skeleton layout (UiIntent).

    LLM replan only when notes request repair or skeleton validation fails.
    """
    first = _plan_layout_skeleton(ctx)
    plan = first["plan"]
    structured = first["structured_content"]
    components = first["requested_components"]
    ok, errors = validate_layout_plan(
        plan,
        goal=ctx.goal or "",
        structured_content=structured,
        requested_components=[],
        final_answer=ctx.final_answer or "",
    )
    if ok and not notes.strip():
        return {
            **first,
            "validation_status": "passed",
            "validation_errors": [],
            "replan_attempted": False,
        }

    replan_attempted = False
    replan_prompt = ""
    replan_llm_output = ""
    merged_usage = dict(first["usage"])

    if _MAX_AUTO_REPLANS > 0 and (not ok or notes.strip()):
        repair_notes = format_validator_notes(errors) if errors else notes
        if notes.strip() and errors:
            repair_notes = f"{notes.strip()}\n\n{repair_notes}"
        elif notes.strip():
            repair_notes = notes.strip()
        second = _plan_layout_llm(
            ctx,
            notes=repair_notes,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        replan_attempted = True
        replan_prompt = second["prompt"]
        replan_llm_output = second["llm_output"]
        merged_usage = _merge_usage(merged_usage, second["usage"])
        plan = second["plan"]
        structured = second["structured_content"]
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        first = {**first, **second, "plan": plan}

    # Last resort: skeleton if LLM still invalid
    if not ok:
        skeleton = _plan_layout_skeleton(ctx)
        plan = skeleton["plan"]
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=[],
            final_answer=ctx.final_answer or "",
        )
        first = {**first, **skeleton, "plan": plan}

    status = "passed" if ok else "failed"
    return {
        **first,
        "plan": plan,
        "usage": merged_usage,
        "validation_status": status,
        "validation_errors": errors,
        "replan_attempted": replan_attempted,
        "replan_prompt": replan_prompt or None,
        "replan_llm_output": replan_llm_output or None,
    }


def build_visual_tools(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: PresentationContext,
):
    """Return Visual Summary Agent tools bound to this run's handoff context."""

    @tool
    def plan_layout(notes: str = "") -> dict[str, Any]:
        """
        Analyze the handoff (goal, main agent answer, evidence) and produce a
        structured layout plan before rendering UI. Call this before render_ui.
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
        return payload

    @tool
    def render_ui(layout_plan_json: str) -> dict[str, Any]:
        """
        Build generative UI blocks from an approved layout plan (JSON string from plan_layout).
        """
        try:
            plan = json.loads(layout_plan_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid layout_plan_json: {e}"}

        if not isinstance(plan, dict):
            return {"error": "layout_plan must be a JSON object"}

        structured = normalize_structured_content(
            ctx.structured_content
            or extract_structured_content(ctx.final_answer or "", goal=ctx.goal or "")
        )
        ok, errors = validate_layout_plan(
            plan,
            goal=ctx.goal or "",
            structured_content=structured,
            requested_components=layout_components_from_goal(ctx.goal or ""),
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

        if int(meta.get("prompt_tokens") or 0) or int(meta.get("completion_tokens") or 0):
            log_usage(
                db,
                user_id=user_id,
                workspace_id=workspace_id,
                kind="visual_summary_render",
                model=meta.get("model") or settings.visual_summary_model,
                prompt_tokens=int(meta.get("prompt_tokens") or 0),
                completion_tokens=int(meta.get("completion_tokens") or 0),
                total_tokens=int(meta.get("total_tokens") or 0),
                meta={"goal": (ctx.goal or "")[:200]},
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

    return [get_current_date, plan_layout, render_ui]