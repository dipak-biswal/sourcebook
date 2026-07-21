"""Phase A — structured handoff validation and resolution for Visual Summary Agent."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.visual_summary.llm_json import STRUCTURED_CONTENT_SCHEMA, chat_json
from app.visual_summary.handoff.structured import extract_structured_content
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


def _strip_md(text: str) -> str:
    """Models leak **bold** into values despite instructions; strip it."""
    return re.sub(r"\*\*", "", text).strip()


def _normalize_str_list(raw: Any, *, item_limit: int = 20, item_chars: int = 400) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        text = _strip_md(str(item))
        if text and text not in out:
            out.append(text[:item_chars])
        if len(out) >= item_limit:
            break
    return out


def _normalize_process_flow(raw: Any) -> dict[str, Any] | None:
    """Sanitize process_flow for flow_diagram assembly; None when unusable."""
    if not isinstance(raw, dict):
        return None
    nodes: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw.get("nodes") or []):
        if not isinstance(item, dict):
            continue
        nid = _strip_md(str(item.get("id") or item.get("label") or f"node_{i}"))[:60]
        label = _strip_md(str(item.get("label") or item.get("id") or ""))[:120]
        if not nid or not label or nid in seen_ids:
            continue
        seen_ids.add(nid)
        entry: dict[str, str] = {"id": nid, "label": label}
        detail = _strip_md(str(item.get("detail") or ""))[:400]
        if detail:
            entry["detail"] = detail
        nodes.append(entry)
        if len(nodes) >= 12:
            break
    if len(nodes) < 2:
        return None
    valid = {n["id"] for n in nodes}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for item in raw.get("edges") or []:
        if not isinstance(item, dict):
            continue
        src = _strip_md(str(item.get("source") or ""))[:60]
        tgt = _strip_md(str(item.get("target") or ""))[:60]
        if not src or not tgt or src not in valid or tgt not in valid:
            continue
        label = _strip_md(str(item.get("label") or ""))[:120]
        key = (src, tgt, label)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edge: dict[str, str] = {"source": src, "target": tgt}
        if label:
            edge["label"] = label
        edges.append(edge)
        if len(edges) >= 20:
            break
    if not edges:
        return None
    return {"nodes": nodes, "edges": edges}


def _normalize_interaction_sequence(raw: Any) -> dict[str, Any] | None:
    """Sanitize interaction_sequence for sequence_diagram; None when unusable."""
    if not isinstance(raw, dict):
        return None
    actors: list[str] = []
    for item in raw.get("actors") or []:
        name = _strip_md(str(item))[:60]
        if name and name not in actors:
            actors.append(name)
        if len(actors) >= 8:
            break
    messages: list[dict[str, Any]] = []
    for i, item in enumerate(raw.get("messages") or []):
        if not isinstance(item, dict):
            continue
        src = _strip_md(str(item.get("source") or ""))[:60]
        tgt = _strip_md(str(item.get("target") or ""))[:60]
        label = _strip_md(str(item.get("label") or ""))[:120]
        if not src or not tgt or not label:
            continue
        for actor in (src, tgt):
            if actor not in actors:
                actors.append(actor)
        try:
            order = int(item.get("order"))
        except (TypeError, ValueError):
            order = i
        msg: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "label": label,
            "order": order,
        }
        note = _strip_md(str(item.get("note") or ""))[:400]
        if note:
            msg["note"] = note
        messages.append(msg)
        if len(messages) >= 24:
            break
    if len(actors) < 2 or not messages:
        return None
    messages.sort(key=lambda m: int(m.get("order", 0)))
    return {"actors": actors[:8], "messages": messages}


def normalize_structured_content(raw: Any) -> dict[str, Any]:
    """Coerce planner/render input to the stable handoff schema (+ optional fields)."""
    if not isinstance(raw, dict):
        return dict(_EMPTY_STRUCTURED)

    summary = _strip_md(str(raw.get("summary") or ""))[:600]
    key_points: list[str] = []
    for item in raw.get("key_points") or []:
        text = _strip_md(str(item))
        if text and text not in key_points:
            key_points.append(text[:400])
        if len(key_points) >= 14:
            break

    faq: list[dict[str, str]] = []
    for item in raw.get("faq") or []:
        if not isinstance(item, dict):
            continue
        question = _strip_md(str(item.get("question") or ""))[:300]
        answer = _strip_md(str(item.get("answer") or ""))[:800]
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
            entry["bullets"] = [
                _strip_md(str(b))[:400] for b in bullets[:8] if _strip_md(str(b))
            ]
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

    # Diagram modules (dict shapes) — previously dropped, so flow/sequence never assembled.
    process_flow = _normalize_process_flow(raw.get("process_flow"))
    if process_flow:
        out["process_flow"] = process_flow
    interaction_sequence = _normalize_interaction_sequence(raw.get("interaction_sequence"))
    if interaction_sequence:
        out["interaction_sequence"] = interaction_sequence

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
    # Explicit bounds — see app/agents/runner/llm.py for why.
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=60.0,
        max_retries=2,
    )


def _format_evidence_block(evidence: Any) -> str:
    """Compact verbatim snippets so extraction can ground visual data in docs."""
    if evidence is None:
        return ""
    lines: list[str] = []
    for hit in (getattr(evidence, "document_hits", None) or [])[:6]:
        snippet = (getattr(hit, "snippet", "") or "").strip()
        if snippet:
            filename = (getattr(hit, "filename", "") or "document").strip()
            lines.append(f"[{filename}] {snippet[:400]}")
    for hit in (getattr(evidence, "web_hits", None) or [])[:4]:
        snippet = (getattr(hit, "snippet", "") or "").strip()
        if snippet:
            title = (getattr(hit, "title", "") or "web").strip()
            lines.append(f"[web: {title[:80]}] {snippet[:300]}")
    if not lines:
        return ""
    return "EVIDENCE SNIPPETS (verbatim from workspace documents / web):\n" + "\n".join(
        lines
    )


def _format_llm_extraction_prompt(
    answer: str,
    *,
    goal: str,
    workspace_block: str = "",
    evidence_block: str = "",
) -> str:
    ws = ""
    if workspace_block.strip():
        ws = f"WORKSPACE CONTEXT:\n{workspace_block.strip()}\n\n"
    ev = f"{evidence_block.strip()}\n\n" if evidence_block.strip() else ""
    return (
        "Extract structured facts for a visual summary from the main workspace "
        "agent answer (and evidence snippets, when present) below.\n"
        "Every fact must appear in the answer or evidence — never invent "
        "employers, skills, metrics, or dates. Omit any field without real data "
        '(use "" or []). Plain text only in values — no markdown bold, bullets, '
        "or numbering. Pipe rows must keep a consistent column count.\n"
        "Return JSON only with this shape:\n"
        "{\n"
        '  "summary": "2-4 sentence overview that answers the user goal",\n'
        '  "key_points": ["short factual bullet", ...],\n'
        '  "ordered_actions": ["Step label — one-line detail", ...],  // only for how-to/process answers\n'
        '  "faq": [{"question": "...", "answer": "..."}],  // only real Q&A pairs with substantive answers\n'
        '  "concepts": ["Term — definition", ...],  // only when the answer defines terms\n'
        '  "levels": ["Skill or area | Strong/Growing/Gap", ...],  // qualitative only — never percentages\n'
        '  "matrix_rows": ["Header A | Header B | Header C", "row | row | row", ...],  // only for a real comparison; first row is the header\n'
        '  "comparisons": ["Aspect | Option A | Option B", ...],\n'
        '  "metrics": ["Label | Value", ...],  // only numbers stated in the answer or evidence\n'
        '  "milestones": ["Period | Title | Detail", ...],  // only when dates appear\n'
        '  "priority_message": "the single most important gap/risk/warning, or \\"\\"",\n'
        '  "process_flow": {"nodes": [{"id": "short_slug", "label": "...", "detail": "concrete role or micro-example (not just restating the label)"}], "edges": [{"source": "id", "target": "id", "label": "..."}]},  // → flow_diagram. REQUIRED when the goal is to explain how a system/mechanism works. Use a LINEAR chain of concrete components (hand-offs A→B→C), not a star with an abstract hub. For the JS event loop prefer nodes call_stack, web_apis, callback_queue, microtask_queue with edges that match the answer — do not add a separate event_loop hub node. detail = what that part does with one concrete example. Every edge source/target must be a listed node id. Omit only when the answer is not mechanism-shaped.\n'
        '  "interaction_sequence": {"actors": ["Name", ...], "messages": [{"source": "Name", "target": "Name", "label": "...", "order": 0, "note": "what happens at this step with a concrete example"}]},  // → sequence_diagram. REQUIRED alongside process_flow for explain/how-it-works goals when the answer includes a concrete example (setTimeout, Promise, request lifecycle, etc.). Actors = the same components as process_flow nodes; messages = ordered steps of that example. Every message source/target must be a listed actor. Omit only when there is truly no multi-step interaction.\n'
        '  "sections": [{"heading": "...", "bullets": ["..."], "body": "..."}],\n'
        '  "themes": ["topical theme", ...]  // 2-6 document topics — never structural labels like "Next Steps" or "Overview"\n'
        "}\n\n"
        f"{ws}"
        f"{ev}"
        f"USER GOAL:\n{(goal or '').strip()}\n\n"
        f"MAIN AGENT ANSWER:\n{(answer or '').strip()[:12000]}"
    )


def format_combined_extract_plan_prompt(
    answer: str,
    *,
    goal: str,
    workspace_block: str = "",
    evidence_block: str = "",
    layout_hints: str = "",
    skeleton_outline: str = "",
) -> str:
    """One prompt: extract structured facts AND plan the layout from them."""
    extraction = _format_llm_extraction_prompt(
        answer,
        goal=goal,
        workspace_block=workspace_block,
        evidence_block=evidence_block,
    )
    outline_block = (
        "REFERENCE SKELETON OUTLINE (from goal/workspace heuristics — optional "
        "starting point; reorder, retitle, or replace freely):\n"
        f"{skeleton_outline}\n\n"
        if skeleton_outline.strip()
        else ""
    )
    hints_block = f"{layout_hints.strip()}\n\n" if layout_hints.strip() else ""
    return (
        "Two tasks in one response.\n\n"
        "TASK 1 — EXTRACT. Follow these extraction rules; put the result in "
        '"structured_content":\n'
        "----\n"
        f"{extraction}\n"
        "----\n\n"
        "TASK 2 — PLAN. From YOUR OWN structured_content, plan the visual "
        'layout; put the result in "layout_plan":\n'
        f"{outline_block}"
        f"{hints_block}"
        "PLAN RULES:\n"
        "- Lead with the block that best answers the user's goal.\n"
        "- For explain / how-it-works / mechanism goals you MUST:\n"
        "  (1) Fill process_flow as a LINEAR handoff chain of concrete components "
        "(e.g. call_stack → web_apis → callback_queue → microtask_queue). "
        "Do NOT invent a separate abstract hub node (e.g. 'event_loop') that only "
        "points at others with no incoming edges — the loop is the process itself.\n"
        "  (2) Fill interaction_sequence with ONE concrete worked example from the "
        "answer (e.g. setTimeout / Promise path) as ordered messages between those "
        "components.\n"
        "  (3) layout_plan block_outline MUST be teaching-only: summary, flow_diagram, "
        "sequence_diagram, and optionally key_terms — in that order. Do NOT plan "
        "key_points, faq, steps, chips, callout, table, or progress for explain goals "
        "even if you extracted those fields (they are for other goal types).\n"
        "  (4) presentation_profile must be mechanism_explainer (never the literal "
        "string short_snake_case).\n"
        "- Every block_outline entry needs type, title, purpose, source_hint, width.\n"
        "- source_hint must name a structured_content field YOU filled with real "
        "data — never an empty one.\n"
        '- width: "full" for wide data (table/comparison/timeline/steps/chips/'
        "summary/flow_diagram/sequence_diagram), \"half\" for compact blocks.\n"
        "- If you filled process_flow, add a block_outline entry with "
        'type "flow_diagram", source_hint "process_flow", width "full". '
        "If you filled interaction_sequence, add one with type "
        '"sequence_diagram", source_hint "interaction_sequence", width "full". '
        "Only ever include these when TASK 1 actually filled that field with "
        "real nodes/edges or actors/messages.\n"
        "- Prefer 4-7 blocks; omit anything without data.\n\n"
        "OUTPUT (JSON only):\n"
        '{"structured_content": {...extraction shape above...},\n'
        ' "layout_plan": {"presentation_profile": "mechanism_explainer", '
        '"components": ["summary", "flow_diagram", ...], "block_outline": '
        '[{"type": "...", "title": "...", "purpose": "...", "source_hint": "...", '
        '"width": "full"}], "rationale": "1-3 sentences"}}'
    )


def extract_structured_content_llm(
    answer: str,
    *,
    goal: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    workspace_packet: Any = None,
    evidence: Any = None,
) -> dict[str, Any] | None:
    """LLM extraction with strict JSON schema; returns None on failure."""
    text = (answer or "").strip()
    if len(text) < 40:
        return None

    workspace_block = ""
    if workspace_packet is not None:
        from app.visual_summary.workspace.context import (
            WorkspaceContextPacket,
            format_workspace_block_for_handoff,
        )

        if isinstance(workspace_packet, WorkspaceContextPacket):
            workspace_block = format_workspace_block_for_handoff(workspace_packet)

    prompt = _format_llm_extraction_prompt(
        text,
        goal=goal,
        workspace_block=workspace_block,
        evidence_block=_format_evidence_block(evidence),
    )
    try:
        resp = chat_json(
            _client(),
            model=settings.visual_summary_model,
            system="You extract structured facts for visual layout planning. JSON only.",
            prompt=prompt,
            schema_name="structured_content",
            schema=STRUCTURED_CONTENT_SCHEMA,
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


def _merge_structured(
    primary: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    """Primary fields win when non-empty; fallback fills anything it missed."""
    merged = dict(fallback)
    for key, value in primary.items():
        if isinstance(value, str):
            if value.strip():
                merged[key] = value
        elif value:
            merged[key] = value
    return merged


def combined_extract_plan_enabled() -> bool:
    """True when extraction + planning run as one LLM call in plan_layout."""
    return bool(
        settings.visual_summary_combined_call
        and settings.visual_summary_llm_planner
        and settings.visual_summary_llm_extractor
        and settings.openai_api_key
    )


def resolve_structured_content(
    answer: str,
    *,
    goal: str = "",
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    workspace_packet: Any = None,
    evidence: Any = None,
) -> tuple[dict[str, Any], str]:
    """
    Resolve structured handoff: LLM extraction first (full visual schema),
    regex heuristic as fallback and gap-filler.

    Returns (structured_content, source) where source is 'heuristic' or 'llm'.

    Combined mode: when the planner will extract+plan in one call, a heuristic
    with substance is returned as-is (no extraction call here) — the combined
    call replaces it during planning. A thin heuristic still gets the separate
    LLM extraction, because handoff validation runs before planning.
    """
    heuristic = normalize_structured_content(
        extract_structured_content(answer, goal=goal)
    )

    if combined_extract_plan_enabled() and structured_content_has_substance(heuristic):
        return heuristic, "heuristic"

    llm_result: dict[str, Any] | None = None
    llm_attempted = False
    if settings.visual_summary_llm_extractor and settings.openai_api_key:
        llm_attempted = True
        llm_result = extract_structured_content_llm(
            answer,
            goal=goal,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_packet=workspace_packet,
            evidence=evidence,
        )
        if llm_result and structured_content_has_substance(llm_result):
            return _merge_structured(llm_result, heuristic), "llm"

    if structured_content_has_substance(heuristic):
        return heuristic, "heuristic"

    # Thin heuristic: try the LLM upgrade unless it already failed above.
    if not llm_attempted:
        llm_result = extract_structured_content_llm(
            answer,
            goal=goal,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_packet=workspace_packet,
            evidence=evidence,
        )
    if llm_result:
        return llm_result, "llm"
    return heuristic, "heuristic"


def handoff_error_message(errors: list[str]) -> str:
    return "; ".join(errors) if errors else "Handoff validation failed."