"""Checkbox-only follow-up questions for a selected curriculum topic."""

from __future__ import annotations

from typing import Any


def intake_questions(
    topic: dict[str, Any],
    *,
    domain: str = "",
) -> dict[str, Any]:
    """Return a form: title, subtitle, questions (checkbox only)."""
    title = str(topic.get("title") or "this topic")
    return {
        "title": f"Set up: {title}",
        "subtitle": "Pick options that fit — no free text. You can change these later in Settings.",
        "questions": [
            {
                "id": "level",
                "prompt": "What depth should we target?",
                "input": "checkbox",
                "required": True,
                "allow_multiple": False,
                "options": [
                    {"id": "beginner", "label": "Beginner"},
                    {"id": "intermediate", "label": "Intermediate"},
                    {"id": "advanced", "label": "Advanced"},
                ],
            },
            {
                "id": "focus",
                "prompt": "What should we emphasize?",
                "input": "checkbox",
                "required": True,
                "allow_multiple": True,
                "options": [
                    {"id": "how_it_works", "label": "How it works"},
                    {"id": "architecture", "label": "Architecture / components"},
                    {"id": "tradeoffs", "label": "Tradeoffs"},
                    {"id": "failure_modes", "label": "Failure modes"},
                    {"id": "interview", "label": "Interview answers"},
                    {"id": "example", "label": "Worked example"},
                ],
            },
            {
                "id": "format",
                "prompt": "Preferred output shape?",
                "input": "checkbox",
                "required": False,
                "allow_multiple": True,
                "options": [
                    {"id": "study_sheet", "label": "Study sheet (numbered sections)"},
                    {"id": "comparisons", "label": "Comparison tables"},
                    {"id": "diagrams", "label": "Flow / sequence diagrams"},
                    {"id": "checklist", "label": "Checklist"},
                ],
            },
            {
                "id": "scope",
                "prompt": "Scope for this run?",
                "input": "checkbox",
                "required": False,
                "allow_multiple": False,
                "options": [
                    {"id": "core", "label": "Core concept only"},
                    {"id": "e2e", "label": "End-to-end system"},
                    {"id": "interview_45", "label": "Interview (≈45 min)"},
                ],
            },
        ],
        "domain": domain,
        "topic_id": topic.get("id"),
        "topic_title": title,
    }


def normalize_answers(
    answers: dict[str, Any] | None,
    questions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Keep only known option ids; checkbox multi → list."""
    q_by_id = {
        str(q.get("id")): q
        for q in questions
        if isinstance(q, dict) and q.get("id")
    }
    out: dict[str, list[str]] = {}
    if not isinstance(answers, dict):
        return out
    for qid, raw in answers.items():
        q = q_by_id.get(str(qid))
        if not q:
            continue
        allowed = {
            str(o.get("id"))
            for o in (q.get("options") or [])
            if isinstance(o, dict) and o.get("id")
        }
        values: list[str] = []
        if isinstance(raw, list):
            values = [str(v).strip() for v in raw if str(v).strip()]
        elif raw is not None and str(raw).strip():
            values = [str(raw).strip()]
        values = [v for v in values if v in allowed]
        if not q.get("allow_multiple") and values:
            values = values[:1]
        if values:
            out[str(qid)] = values
    return out


def validate_required(
    answers: dict[str, list[str]],
    questions: list[dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    for q in questions:
        if not isinstance(q, dict) or not q.get("required"):
            continue
        qid = str(q.get("id") or "")
        if not answers.get(qid):
            missing.append(qid)
    return missing
