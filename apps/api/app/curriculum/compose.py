"""Compose main-agent goal + context block from topic + preferences."""

from __future__ import annotations

from typing import Any

from app.agents.visual_summary.planning.intent_recipes import (
    content_contract_for_prompt,
    resolve_recipe,
)

_LEVEL_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}
_FOCUS_LABELS = {
    "how_it_works": "how it works",
    "architecture": "architecture and components",
    "tradeoffs": "tradeoffs",
    "failure_modes": "failure modes and recovery",
    "interview": "interview-style answers",
    "example": "a concrete worked example",
}
_FORMAT_LABELS = {
    "study_sheet": "numbered study sheet sections",
    "comparisons": "comparison tables",
    "diagrams": "process/sequence diagrams (describe as A → B → C chains)",
    "checklist": "actionable checklists",
}
_SCOPE_LABELS = {
    "core": "core concept only",
    "e2e": "end-to-end system view",
    "interview_45": "depth suitable for a ~45 minute interview discussion",
}


def _labels(ids: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping.get(i, i.replace("_", " ")) for i in ids if i]


def compose_goal(
    topic: dict[str, Any],
    *,
    preferences: dict[str, list[str]] | None = None,
    domain: str = "",
) -> str:
    prefs = preferences if isinstance(preferences, dict) else (topic.get("preferences") or {})
    title = str(topic.get("title") or "this topic").strip()
    level = _labels(prefs.get("level") or [], _LEVEL_LABELS)
    focus = _labels(prefs.get("focus") or [], _FOCUS_LABELS)
    fmt = _labels(prefs.get("format") or [], _FORMAT_LABELS)
    scope = _labels(prefs.get("scope") or [], _SCOPE_LABELS)

    # Default format for teaching boards
    if not fmt:
        fmt = [_FORMAT_LABELS["study_sheet"], _FORMAT_LABELS["diagrams"]]

    parts = [
        f"Create a complete study sheet for: {title}.",
    ]
    if domain:
        parts.append(f"Workspace domain: {domain}.")
    if level:
        parts.append(f"Level: {', '.join(level)}.")
    if focus:
        parts.append(f"Emphasize: {', '.join(focus)}.")
    if fmt:
        parts.append(f"Format: {', '.join(fmt)}.")
    if scope:
        parts.append(f"Scope: {', '.join(scope)}.")
    recipe = resolve_recipe(
        goal=f"study sheet {title}",
        topic_title=title,
        preferences=prefs,
    )
    parts.append(
        "Structure the answer as numbered markdown sections "
        "(## 1. Title, ## 2. Title, …). "
        "Be concrete: real component names, real metrics, no filler."
    )
    contract = content_contract_for_prompt(recipe)
    if contract:
        parts.append("\n\n" + contract)
    return " ".join(parts).replace("\n\n ", "\n\n")


def compose_context_block(
    topic: dict[str, Any],
    *,
    preferences: dict[str, list[str]] | None = None,
    domain: str = "",
) -> str:
    prefs = preferences if isinstance(preferences, dict) else (topic.get("preferences") or {})
    lines = [
        "CURRICULUM SELECTION (user-chosen topic)",
        f"- Topic: {topic.get('title')}",
        f"- Topic id: {topic.get('id')}",
    ]
    if domain:
        lines.append(f"- Domain: {domain}")
    if topic.get("summary"):
        lines.append(f"- Summary: {topic.get('summary')}")
    if prefs:
        for k, vals in prefs.items():
            if vals:
                lines.append(f"- {k}: {', '.join(vals)}")
    lines.append(
        "Honor these preferences when teaching. Prefer study-sheet structure "
        "and diagram-friendly descriptions."
    )
    recipe = resolve_recipe(
        goal=str(topic.get("title") or ""),
        topic_title=str(topic.get("title") or ""),
        preferences=prefs,
    )
    contract = content_contract_for_prompt(recipe)
    if contract:
        lines.append("")
        lines.append(contract)
    return "\n".join(lines)
