"""Parse user goals for requested visual-summary components."""

from __future__ import annotations

import re

_COMPONENT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btable\b", re.I), "table"),
    (re.compile(r"progress\s*bar|progress\b", re.I), "progress"),
    (re.compile(r"\bchart\b", re.I), "chart"),
    (re.compile(r"\bchips?\b|filterable|filter\s+chip", re.I), "chips"),
    (re.compile(r"callout|main\s+gap", re.I), "callout"),
    (re.compile(r"\btimeline\b|milestones?", re.I), "timeline"),
    (re.compile(r"\bfaq\b", re.I), "faq"),
    (re.compile(r"key\s*points?", re.I), "key_points"),
    (re.compile(r"comparison|side\s+by\s+side", re.I), "comparison"),
    (re.compile(r"glossary|key\s+terms?", re.I), "key_terms"),
)

_COMPONENT_GUIDE: dict[str, str] = {
    "table": "Pipe-separated rows; first row = column headers (e.g. Skill | Level | Gap)",
    "progress": (
        "Items as Label | Level using Strong, Growing, Foundational, Gap, etc. "
        "— NOT numeric % unless the answer states a number"
    ),
    "chart": "Same qualitative levels as progress (Label | Strong), ranked by fit",
    "chips": "Theme labels as Label|slug; tag related blocks with tags: [slug]",
    "callout": "body = main gap or key insight; short title",
    "timeline": "Only if answer lists explicit dates/roles; Period | Role | Detail",
    "faq": "At least 3 faq items from answer themes",
    "key_points": "Bullet highlights from structured content — no prose dump",
    "comparison": "Side-by-side columns from answer",
    "key_terms": "Glossary terms drawn from answer",
}


def layout_components_from_goal(goal: str) -> list[str]:
    """Ordered unique component types the user asked for in their goal."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern, typ in _COMPONENT_RULES:
        if pattern.search(goal) and typ not in seen:
            seen.add(typ)
            out.append(typ)
    return out


def format_layout_requirements(components: list[str]) -> str:
    if not components:
        return (
            "LAYOUT: Choose components that best fit the goal and agent answer. "
            "Agent answer provides FACTS only — you decide structure."
        )
    lines = [
        "REQUESTED UI COMPONENTS (user goal — you MUST include each block below when grounded):",
    ]
    for typ in components:
        guide = _COMPONENT_GUIDE.get(typ, typ)
        lines.append(f"  • {typ}: {guide}")
    lines.append(
        "Populate from structured content passed to the planner. "
        "Do NOT echo UI component names from the answer as content."
    )
    return "\n".join(lines)