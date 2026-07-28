"""Generate and cache textbook-style lessons for the Learn page.

Shape mirrors ml-visualized: long-form sections + figure blocks for a
right-rail visual panel. Lessons are stored under curriculum.lessons[topic_id].
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.curriculum.domain import domain_label
from app.curriculum.schema import find_topic
from app.curriculum.service import get_curriculum, save_curriculum
from app.models import Workspace
from app.usage import estimate_tokens, log_usage

_LESSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "prerequisites": {
            "type": "array",
            "items": {"type": "string"},
        },
        "key_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "definition": {"type": "string"},
                },
                "required": ["term", "definition"],
                "additionalProperties": False,
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "heading": {"type": "string"},
                    "body_md": {"type": "string"},
                    "visual_id": {"type": "string"},
                },
                "required": ["id", "heading", "body_md", "visual_id"],
                "additionalProperties": False,
            },
        },
        "visuals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "summary",
                            "key_points",
                            "steps",
                            "table",
                            "comparison",
                            "flow_diagram",
                            "callout",
                            "metrics",
                            "option_cards",
                        ],
                    },
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["id", "type", "title", "body", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "title",
        "summary",
        "prerequisites",
        "key_terms",
        "sections",
        "visuals",
    ],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s[:48] or "section"


def normalize_lesson(raw: Any) -> dict[str, Any] | None:
    """Coerce LLM / cached lesson into a stable API shape."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None

    prereqs: list[str] = []
    for p in raw.get("prerequisites") or []:
        t = str(p).strip()
        if t and t not in prereqs:
            prereqs.append(t[:200])
        if len(prereqs) >= 8:
            break

    key_terms: list[dict[str, str]] = []
    for kt in raw.get("key_terms") or []:
        if not isinstance(kt, dict):
            continue
        term = str(kt.get("term") or "").strip()
        definition = str(kt.get("definition") or "").strip()
        if term and definition:
            key_terms.append({"term": term[:80], "definition": definition[:400]})
        if len(key_terms) >= 12:
            break

    visuals_in = raw.get("visuals") or []
    visuals: list[dict[str, Any]] = []
    seen_vid: set[str] = set()
    if isinstance(visuals_in, list):
        for v in visuals_in:
            if not isinstance(v, dict):
                continue
            vid = str(v.get("id") or "").strip() or f"v{len(visuals) + 1}"
            if vid in seen_vid:
                continue
            seen_vid.add(vid)
            vtype = str(v.get("type") or "key_points").strip()
            items = [
                str(i).strip()[:400]
                for i in (v.get("items") or [])
                if str(i).strip()
            ][:12]
            visuals.append(
                {
                    "id": vid[:40],
                    "type": vtype[:40],
                    "title": str(v.get("title") or "Figure")[:120],
                    "body": str(v.get("body") or "").strip()[:800] or None,
                    "items": items or None,
                    "width": "full",
                }
            )
            if len(visuals) >= 10:
                break

    sections: list[dict[str, Any]] = []
    for i, sec in enumerate(raw.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading") or "").strip()
        body = str(sec.get("body_md") or sec.get("body") or "").strip()
        if not heading or not body:
            continue
        sid = str(sec.get("id") or "").strip() or _slug(heading)
        visual_id = str(sec.get("visual_id") or "").strip() or None
        if visual_id and visual_id not in seen_vid:
            # Keep link only when visual exists.
            visual_id = None
        sections.append(
            {
                "id": sid[:48],
                "heading": heading[:160],
                "body_md": body[:6000],
                "visual_id": visual_id,
            }
        )
        if len(sections) >= 12:
            break

    if len(sections) < 2:
        return None

    outline = [{"id": s["id"], "heading": s["heading"]} for s in sections]

    return {
        "title": title[:160],
        "summary": str(raw.get("summary") or "").strip()[:600],
        "prerequisites": prereqs,
        "key_terms": key_terms,
        "outline": outline,
        "sections": sections,
        "visuals": visuals,
        "generated_at": str(raw.get("generated_at") or _now_iso()),
        "cached": bool(raw.get("cached")),
    }


def _fallback_lesson(topic: dict[str, Any], domain: str) -> dict[str, Any]:
    title = str(topic.get("title") or "Topic")
    summary = str(topic.get("summary") or f"An introduction to {title}.")
    return normalize_lesson(
        {
            "title": title,
            "summary": summary,
            "prerequisites": [f"Basic familiarity with {domain or 'the domain'}"],
            "key_terms": [
                {
                    "term": title,
                    "definition": summary or f"Core idea behind {title}.",
                }
            ],
            "sections": [
                {
                    "id": "why",
                    "heading": f"Why {title} matters",
                    "body_md": (
                        f"**{title}** is a practical concept in {domain or 'this domain'}.\n\n"
                        f"{summary}\n\n"
                        "This lesson is a lightweight fallback while a full AI lesson "
                        "is unavailable. Refresh to regenerate when the model is ready."
                    ),
                    "visual_id": "v1",
                },
                {
                    "id": "how",
                    "heading": "How it works",
                    "body_md": (
                        f"At a high level, {title} breaks into a few named pieces:\n\n"
                        "1. Inputs and context\n"
                        "2. Core mechanism\n"
                        "3. Outputs and side effects\n\n"
                        "Map each piece to a real component name when you study further."
                    ),
                    "visual_id": "v2",
                },
                {
                    "id": "practice",
                    "heading": "When to use it",
                    "body_md": (
                        f"Use **{title}** when you need a reliable approach under real "
                        "constraints. Prefer a simpler alternative when the problem is "
                        "small or the operational cost is not justified."
                    ),
                    "visual_id": "v3",
                },
            ],
            "visuals": [
                {
                    "id": "v1",
                    "type": "callout",
                    "title": "Focus",
                    "body": summary or f"Learn {title} end to end.",
                    "items": [],
                },
                {
                    "id": "v2",
                    "type": "flow_diagram",
                    "title": "High-level flow",
                    "body": "",
                    "items": [
                        "Context → Mechanism → Result",
                        "Input | Process | Output",
                    ],
                },
                {
                    "id": "v3",
                    "type": "key_points",
                    "title": "Remember",
                    "body": "",
                    "items": [
                        "Name real components, not placeholders",
                        "Know when NOT to use this approach",
                        "Prefer concrete examples over abstractions",
                    ],
                },
            ],
            "generated_at": _now_iso(),
        }
    ) or {
        "title": title,
        "summary": summary,
        "prerequisites": [],
        "key_terms": [],
        "outline": [],
        "sections": [],
        "visuals": [],
        "generated_at": _now_iso(),
        "cached": False,
    }


def _generate_lesson_llm(
    *,
    topic: dict[str, Any],
    domain: str,
    workspace: Workspace,
    db: Session,
    user_id: Any,
) -> dict[str, Any] | None:
    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    title = str(topic.get("title") or "Topic")
    summary = str(topic.get("summary") or "")
    tags = ", ".join(str(t) for t in (topic.get("tags") or [])[:6])
    kind = str(topic.get("kind") or "").strip().lower()
    is_chapter = kind == "chapter" or not topic.get("parent_id")
    role = (
        "CHAPTER INTRODUCTION — overview of this area, why it matters, "
        "mental model, and a map of subtopics the learner will study next"
        if is_chapter
        else "FOCUSED LESSON — deep dive on this specific technique/concept"
    )
    prompt = (
        f"Domain: {domain}\n"
        f"Topic: {title}\n"
        f"Topic summary: {summary}\n"
        f"Tags: {tags or '(none)'}\n"
        f"Role: {role}\n\n"
        "Write a textbook-quality learning lesson (ml-visualized style):\n"
        "- 6–10 numbered teaching sections with markdown body_md\n"
        "- Concrete names, formulas or code when relevant, pipe tables in prose\n"
        "- Each section may link visual_id to a figure in visuals[]\n"
        "- visuals: 3–6 figures (flow_diagram, table, key_points, steps, "
        "comparison, option_cards, callout, metrics)\n"
        "- For flow/table/comparison use items as pipe rows or A → B → C chains\n"
        "- prerequisites (2–4) and key_terms (4–8)\n"
        "- No UI chrome talk; pure teaching content\n"
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=(
                "You are an expert technical teacher. Output only JSON matching the "
                "schema. Be dense, concrete, and scannable — like a polished chapter."
            ),
            prompt=prompt,
            schema_name="learn_lesson",
            schema=_LESSON_SCHEMA,
            temperature=0.35,
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
    if not parsed.get("title"):
        parsed["title"] = title
    if not parsed.get("summary"):
        parsed["summary"] = summary
    parsed["generated_at"] = _now_iso()

    if user_id is not None:
        usage = getattr(resp, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
        if pt == 0 and ct == 0:
            pt = estimate_tokens(prompt)
            ct = estimate_tokens(raw)
        try:
            log_usage(
                db,
                user_id=user_id,
                workspace_id=workspace.id,
                kind="learn_lesson",
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=pt + ct,
                meta={"topic_id": topic.get("id"), "title": title[:80]},
            )
        except Exception:
            pass

    return normalize_lesson(parsed)


def get_or_generate_lesson(
    db: Session,
    workspace: Workspace,
    topic_id: str,
    *,
    user_id: Any = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Return a lesson for topic_id. Uses cache unless force=True.
    Ensures curriculum topics exist (caller should discover first when empty).
    """
    cur = get_curriculum(workspace)
    topic = find_topic(cur, topic_id)
    if not topic:
        raise KeyError(topic_id)

    lessons = cur.get("lessons") if isinstance(cur.get("lessons"), dict) else {}
    cached = lessons.get(str(topic.get("id") or topic_id))
    if not force and isinstance(cached, dict):
        norm = normalize_lesson({**cached, "cached": True})
        if norm:
            return norm

    domain = str(cur.get("domain") or "") or domain_label(
        name=workspace.name or "",
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
    )

    lesson = _generate_lesson_llm(
        topic=topic,
        domain=domain,
        workspace=workspace,
        db=db,
        user_id=user_id,
    )
    if not lesson:
        lesson = _fallback_lesson(topic, domain)
        lesson["cached"] = False
        lesson["fallback"] = True
    else:
        lesson["cached"] = False
        lesson["fallback"] = False

    # Persist cache
    lessons = dict(lessons)
    store = dict(lesson)
    store.pop("cached", None)
    lessons[str(topic.get("id") or topic_id)] = store
    cur = dict(cur)
    cur["lessons"] = lessons
    save_curriculum(db, workspace, cur)

    return lesson
