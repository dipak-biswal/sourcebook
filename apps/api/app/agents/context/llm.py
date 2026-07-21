"""Small-LLM question generation for the context collector."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.agents.context.questions import (
    default_form_subtitle,
    default_form_title,
    normalize_questions,
    template_questions_for_gaps,
)
from app.agents.context.readiness import Gap
from app.agents.visual_summary.llm_json import chat_json
from app.agents.visual_summary.workspace.context import WorkspaceContextPacket
from app.config import settings

logger = logging.getLogger(__name__)

QUESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "prompt": {"type": "string"},
                    "input": {"type": "string", "enum": ["text", "checkbox"]},
                    "required": {"type": "boolean"},
                    "placeholder": {"type": "string"},
                    "allow_multiple": {"type": "boolean"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["id", "label"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "id",
                    "prompt",
                    "input",
                    "required",
                    "placeholder",
                    "allow_multiple",
                    "options",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "subtitle", "questions"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You prepare a short form that collects missing context so a research/"
    "teaching agent can run well. The workspace can be about ANY topic.\n"
    "Rules:\n"
    "- Ask ONLY about the listed gaps — do not invent new product features.\n"
    "- Prefer checkboxes for closed choices (level, audience, document plan).\n"
    "- Prefer text for free detail (topic focus, URLs, constraints).\n"
    "- Max 4 questions. Keep prompts short and domain-agnostic.\n"
    "- Never assume a vertical (resume, JS, etc.) unless the goal says so.\n"
    "- For checkbox questions include 2–6 options with stable snake_case ids.\n"
    "- For text questions set options to [] and allow_multiple to false.\n"
    "Return JSON matching the schema only."
)


def _model_name() -> str:
    return (settings.context_agent_model or "").strip() or settings.chat_model


def _packet_summary(packet: WorkspaceContextPacket) -> str:
    i = packet.identity
    e = packet.evidence
    d = packet.derived
    return (
        f"Name: {i.name or '(unnamed)'}\n"
        f"Description: {(i.description or '')[:500] or '(none)'}\n"
        f"Tags: {', '.join(i.tags) or '(none)'}\n"
        f"Confidence: {packet.meta.confidence}\n"
        f"Outcome: {d.outcome_phrase}\n"
        f"Audience: {d.audience_phrase}\n"
        f"Ready docs ({len(e.documents_ready)}): "
        f"{', '.join(e.documents_ready[:8]) or '(none)'}\n"
        f"External/web allowed: {d.tool_policy.external_context_ok}"
    )


def _user_prompt(packet: WorkspaceContextPacket, goal: str, gaps: list[Gap]) -> str:
    gap_lines = "\n".join(f"- {g.id}: {g.reason}" for g in gaps)
    return (
        f"USER GOAL:\n{goal.strip()}\n\n"
        f"WORKSPACE:\n{_packet_summary(packet)}\n\n"
        f"GAPS TO ADDRESS:\n{gap_lines}\n\n"
        "Produce a form title, optional subtitle, and questions that fill these gaps."
    )


def generate_questions(
    packet: WorkspaceContextPacket,
    goal: str,
    gaps: list[Gap],
    *,
    max_questions: int | None = None,
) -> dict[str, Any]:
    """
    Return {title, subtitle, questions} for pending_tool.args.

    Uses a small LLM when enabled; falls back to templates on any failure.
    """
    cap = max_questions or int(getattr(settings, "context_agent_max_questions", 4) or 4)
    templates = template_questions_for_gaps(
        gaps, packet, goal, max_questions=cap
    )
    form = {
        "title": default_form_title(gaps),
        "subtitle": default_form_subtitle(),
        "questions": templates,
    }

    if not gaps:
        return form

    use_llm = bool(getattr(settings, "context_agent_llm", True))
    if not use_llm or not settings.openai_api_key:
        return form

    try:
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        resp = chat_json(
            client,
            model=_model_name(),
            system=_SYSTEM,
            prompt=_user_prompt(packet, goal, gaps),
            schema_name="context_questions",
            schema=QUESTIONS_SCHEMA,
            temperature=0.2,
            max_tokens=800,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content) if content else {}
        if not isinstance(data, dict):
            return form
        questions = normalize_questions(data.get("questions") or [], max_questions=cap)
        if not questions:
            return form
        title = str(data.get("title") or "").strip() or form["title"]
        subtitle = str(data.get("subtitle") or "").strip() or form["subtitle"]
        return {
            "title": title[:200],
            "subtitle": subtitle[:300],
            "questions": questions,
        }
    except Exception:
        logger.exception(
            "context agent LLM question generation failed; using templates"
        )
        return form
