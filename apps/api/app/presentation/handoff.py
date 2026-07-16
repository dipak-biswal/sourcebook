"""Phase A — structured handoff validation and resolution for Visual Summary Agent."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.presentation.structured import extract_structured_content
from app.usage import estimate_tokens, log_usage

STRUCTURED_CONTENT_KEYS = frozenset(
    {"summary", "key_points", "faq", "sections", "themes"}
)

# Optional fields used by assemble_block / available_source_hints — preserved when present.
_OPTIONAL_LIST_FIELDS = (
    "matrix_rows",
    "comparisons",
    "levels",
    "concepts",
    "terms",
    "ordered_actions",
    "learning_path",
    "design_process",
    "steps",
    "update_checklist",
    "milestones",
    "timeline",
    "metrics",
    "gaps",
    "risks",
    "misconceptions",
)
_OPTIONAL_STR_FIELDS = ("priority_message",)

_EMPTY_STRUCTURED: dict[str, Any] = {
    "summary": "",
    "key_points": [],
    "faq": [],
    "sections": [],
    "themes": [],
}


def _normalize_str_list(raw: Any, *, item_limit: int = 20, item_chars: int = 400) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text[:item_chars])
        if len(out) >= item_limit:
            break
    return out


def normalize_structured_content(raw: Any) -> dict[str, Any]:
    """Coerce planner/render input to the stable handoff schema (+ optional fields)."""
    if not isinstance(raw, dict):
        return dict(_EMPTY_STRUCTURED)

    summary = str(raw.get("summary") or "").strip()[:600]
    key_points: list[str] = []
    for item in raw.get("key_points") or []:
        text = str(item).strip()
        if text and text not in key_points:
            key_points.append(text[:400])
        if len(key_points) >= 14:
            break

    faq: list[dict[str, str]] = []
    for item in raw.get("faq") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()[:300]
        answer = str(item.get("answer") or "").strip()[:800]
        if question:
            faq.append({"question": question, "answer": answer})
        if len(faq) >= 10:
            break

    sections: list[dict[str, Any]] = []
    for item in raw.get("sections") or []:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading") or "").strip()[:120]
        if not heading:
            continue
        entry: dict[str, Any] = {"heading": heading}
        bullets = item.get("bullets")
        if isinstance(bullets, list) and bullets:
            entry["bullets"] = [str(b).strip()[:400] for b in bullets[:8] if str(b).strip()]
        body = str(item.get("body") or "").strip()
        if body:
            entry["body"] = body[:1200]
        sections.append(entry)
        if len(sections) >= 8:
            break

    themes: list[str] = []
    for item in raw.get("themes") or []:
        text = str(item).strip()[:60]
        if text and text not in themes:
            themes.append(text)
        if len(themes) >= 6:
            break

    out: dict[str, Any] = {
        "summary": summary,
        "key_points": key_points,
        "faq": faq,
        "sections": sections,
        "themes": themes,
    }

    # Preserve extended fields so planner grounding + assembly can use them.
    for key in _OPTIONAL_LIST_FIELDS:
        items = _normalize_str_list(raw.get(key))
        if items:
            out[key] = items
    for key in _OPTIONAL_STR_FIELDS:
        text = str(raw.get(key) or "").strip()
        if text:
            out[key] = text[:800]

    return out


def validate_handoff(structured: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """
    Fail fast when structured content is too thin for visual planning.

    Requires at least one of: non-empty summary, key_points, or faq.
    """
    data = normalize_structured_content(structured)
    errors: list[str] = []
    has_summary = bool((data.get("summary") or "").strip())
    has_key_points = bool(data.get("key_points"))
    has_faq = bool(data.get("faq"))
    has_sections = bool(data.get("sections"))

    if not (has_summary or has_key_points or has_faq):
        errors.append(
            "Handoff is too thin: need a summary, key_points, or faq from the main agent answer."
        )
    if not has_summary and not has_key_points and has_sections:
        errors.append(
            "Sections alone are not enough — add a summary or key_points in the main answer."
        )
    return (len(errors) == 0, errors)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _format_llm_extraction_prompt(
    answer: str,
    *,
    goal: str,
    workspace_block: str = "",
) -> str:
    ws = ""
    if workspace_block.strip():
        ws = f"WORKSPACE CONTEXT:\n{workspace_block.strip()}\n\n"
    return (
        "Extract structured content from the main workspace agent answer below.\n"
        "Use ONLY facts present in the answer — do not invent employers, metrics, or dates.\n"
        "Prefer structure that supports the workspace outcome and tone when facts allow.\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "summary": "2-4 sentence overview",\n'
        '  "key_points": ["bullet", ...],\n'
        '  "faq": [{"question": "...", "answer": "..."}],\n'
        '  "sections": [{"heading": "...", "bullets": ["..."], "body": "..."}],\n'
        '  "themes": ["theme", ...]\n'
        "}\n\n"
        f"{ws}"
        f"USER GOAL:\n{(goal or '').strip()}\n\n"
        f"MAIN AGENT ANSWER:\n{(answer or '').strip()[:12000]}"
    )


def extract_structured_content_llm(
    answer: str,
    *,
    goal: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    workspace_packet: Any = None,
) -> dict[str, Any] | None:
    """LLM extraction with strict JSON schema; returns None on failure."""
    text = (answer or "").strip()
    if len(text) < 40:
        return None

    workspace_block = ""
    if workspace_packet is not None:
        from app.presentation.workspace_context import (
            WorkspaceContextPacket,
            format_workspace_block_for_handoff,
        )

        if isinstance(workspace_packet, WorkspaceContextPacket):
            workspace_block = format_workspace_block_for_handoff(workspace_packet)

    prompt = _format_llm_extraction_prompt(
        text, goal=goal, workspace_block=workspace_block
    )
    try:
        resp = _client().chat.completions.create(
            model=settings.visual_summary_model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured facts for visual layout planning. JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
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

    if db is not None and user_id is not None and workspace_id is not None:
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(raw)
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_extract",
            model=settings.visual_summary_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            meta={"goal": (goal or "")[:200]},
        )

    return normalize_structured_content(parsed)


def structured_content_has_substance(structured: dict[str, Any]) -> bool:
    ok, _ = validate_handoff(structured)
    return ok


def resolve_structured_content(
    answer: str,
    *,
    goal: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    workspace_packet: Any = None,
) -> tuple[dict[str, Any], str]:
    """
    Resolve structured handoff: heuristic first, LLM upgrade when thin.

    Returns (structured_content, source) where source is 'heuristic' or 'llm'.
    """
    heuristic = normalize_structured_content(
        extract_structured_content(answer, goal=goal)
    )
    if structured_content_has_substance(heuristic):
        return heuristic, "heuristic"

    llm_result = extract_structured_content_llm(
        answer,
        goal=goal,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        workspace_packet=workspace_packet,
    )
    if llm_result and structured_content_has_substance(llm_result):
        return llm_result, "llm"

    if llm_result:
        return llm_result, "llm"
    return heuristic, "heuristic"


def handoff_error_message(errors: list[str]) -> str:
    return "; ".join(errors) if errors else "Handoff validation failed."