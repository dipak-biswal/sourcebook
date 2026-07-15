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
    components = layout_components_from_goal(goal)
    layout_hints = format_layout_requirements(components)
    planner_input = build_plan_layout_input(
        goal=goal,
        structured_content=structured,
        evidence=ctx.agent_evidence,
        components=components,
        notes=notes,
    )
    prompt = format_plan_layout_prompt(planner_input, layout_hints=layout_hints)

    client = _client()
    resp = client.chat.completions.create(
        model=settings.visual_summary_model,
        messages=[
            {"role": "system", "content": "You plan visual summary layouts. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        plan = {
            "presentation_profile": "fallback_markdown",
            "components": components,
            "block_outline": [],
            "rationale": "Fallback plan — model returned invalid JSON.",
        }

    if not isinstance(plan, dict):
        plan = {}
    plan.setdefault("components", components)
    plan.setdefault("presentation_profile", "general_summary")
    plan.setdefault("block_outline", [])
    plan.setdefault("rationale", "")

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
    }


def _plan_with_validation(
    ctx: PresentationContext,
    *,
    notes: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Run planner LLM, validate, and auto-replan once on validator failure."""
    first = _plan_layout_llm(
        ctx,
        notes=notes,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    plan = first["plan"]
    structured = first["structured_content"]
    components = first["requested_components"]
    ok, errors = validate_layout_plan(
        plan,
        goal=ctx.goal or "",
        structured_content=structured,
        requested_components=components,
        final_answer=ctx.final_answer or "",
    )
    if ok:
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

    if _MAX_AUTO_REPLANS > 0:
        repair_notes = format_validator_notes(errors)
        if notes.strip():
            repair_notes = f"{notes.strip()}\n\n{repair_notes}"
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
            requested_components=components,
            final_answer=ctx.final_answer or "",
        )
        first = second

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
        )
        spec, meta = build_presentation(db, render_ctx)
        if isinstance(spec, dict) and spec.get("error"):
            return {"error": spec.get("error"), "meta": meta}

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
        }

    return [get_current_date, plan_layout, render_ui]