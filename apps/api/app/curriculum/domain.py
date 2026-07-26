"""Detect learning/curriculum workspaces from name, description, tags (no hardcode vertical)."""

from __future__ import annotations

import re
from typing import Any

_LEARN_RE = re.compile(
    r"\b("
    r"learn|learning|study|studying|teach|teaching|course|curriculum|"
    r"interview\s*prep|concepts?|fundamentals|system\s*design|"
    r"distributed|dsa|algorithms?|data\s*structures?|"
    r"tutorial|guide|master|understand|explain"
    r")\b",
    re.I,
)

_LEARN_TAGS = frozenset(
    {
        "learning",
        "study",
        "education",
        "interview",
        "system-design",
        "system_design",
        "dsa",
        "course",
        "concepts",
    }
)


def workspace_text_blob(
    *,
    name: str = "",
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    parts = [name or ""]
    if description:
        parts.append(description)
    if tags:
        parts.extend(str(t) for t in tags if t)
    return "\n".join(parts)


def is_curriculum_workspace(
    *,
    name: str = "",
    description: str | None = None,
    tags: list[str] | None = None,
    packet: dict[str, Any] | None = None,
) -> bool:
    """
    True when this workspace should show a topic catalog.

    Derived from user-written context — not a fixed "system design" product mode.
    """
    tag_set = {str(t).strip().lower() for t in (tags or []) if t and str(t).strip()}
    if tag_set & _LEARN_TAGS:
        return True
    blob = workspace_text_blob(name=name, description=description, tags=tags)
    if _LEARN_RE.search(blob):
        return True
    if isinstance(packet, dict):
        derived = packet.get("derived") if isinstance(packet.get("derived"), dict) else {}
        outcome = str(derived.get("outcome_phrase") or "").lower()
        if any(k in outcome for k in ("learn", "understand", "study", "master", "explain")):
            return True
        affs = derived.get("visual_affordances") or []
        if isinstance(affs, list):
            joined = " ".join(str(a) for a in affs).lower()
            if "concept" in joined or "ordered_guide" in joined or "mechanism" in joined:
                return True
    return False


def domain_label(
    *,
    name: str = "",
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Short domain string used for search + topic discovery prompts."""
    n = (name or "").strip()
    if n:
        return n[:80]
    if description:
        first = description.strip().split("\n")[0].strip()
        if first:
            return first[:80]
    if tags:
        return ", ".join(str(t) for t in tags[:3] if t)[:80]
    return "general learning"
