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
from app.presentation.layout import format_layout_requirements, layout_components_from_goal
from app.presentation.structured import (
    build_plan_layout_input,
    extract_structured_content,
    format_plan_layout_prompt,
)
from app.usage import estimate_tokens, log_usage

VISUAL_SUMMARY_AGENT_LABEL = "Visual Summary Agent"


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _plan_layout_llm(ctx: PresentationContext, *, notes: str = "") -> dict[str, Any]:
    goal = (ctx.goal or "").strip()
    structured = ctx.structured_content or extract_structured_content(
        ctx.final_answer or "",
        goal=goal,
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

    return {
        "plan": plan,
        "structured_input": planner_input,
        "prompt": prompt,
        "llm_output": raw,
        "usage": {
            "model": settings.visual_summary_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
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
        result = _plan_layout_llm(ctx, notes=notes)
        usage = result["usage"]
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_plan",
            model=usage["model"],
            prompt_tokens=int(usage["prompt_tokens"] or 0),
            completion_tokens=int(usage["completion_tokens"] or 0),
            total_tokens=int(usage["total_tokens"] or 0),
            meta={"goal": (ctx.goal or "")[:200]},
        )
        return {
            "status": "planned",
            "layout_plan": result["plan"],
            "structured_input": result.get("structured_input"),
            "model": usage["model"],
            "prompt": result["prompt"],
            "llm_output": result["llm_output"],
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
        }

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
            structured_content=ctx.structured_content,
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