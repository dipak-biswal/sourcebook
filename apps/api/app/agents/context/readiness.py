"""Pure readiness assessment: does the main agent have enough context?

No LLM, no DB — only packet + goal. Keeps the happy path free of extra latency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.visual_summary.workspace.context import WorkspaceContextPacket

# Goal words that imply the user expects workspace documents as evidence.
_DOC_IMPLIED = (
    "my notes",
    "my documents",
    "my docs",
    "my resume",
    "my cv",
    "my file",
    "uploaded",
    "based on my",
    "from my documents",
    "in my workspace",
    "using my notes",
)

# Goal patterns that usually need scoped research when docs are thin.
_LEARN_OR_EXPLAIN = (
    "learn",
    "explain",
    "teach",
    "understand",
    "how does",
    "how do",
    "what is",
    "what are",
    "tutorial",
    "walk me through",
    "overview of",
)

_AUDIENCE_HINTS = (
    "for beginners",
    "for experts",
    "for my team",
    "interview",
    "audience",
    "for kids",
    "for students",
)

_URL_IN_GOAL = re.compile(r"https?://\S+", re.I)
_URL_REFERENCE = re.compile(
    r"\b(this (article|page|link|url|post|blog)|the (article|link|url) (above|below))\b",
    re.I,
)

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "my",
        "me",
        "i",
        "to",
        "of",
        "in",
        "on",
        "for",
        "and",
        "or",
        "please",
        "help",
        "with",
        "about",
        "explain",
        "learn",
        "show",
        "tell",
        "give",
        "how",
        "what",
        "why",
        "does",
        "do",
        "is",
        "are",
        "it",
        "this",
        "that",
    }
)


@dataclass(frozen=True)
class Gap:
    """One missing piece of context the collector should address."""

    id: str
    reason: str
    severity: str = "medium"  # low | medium | high


def _goal_tokens(goal: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", (goal or "").lower())


def _substantive_tokens(goal: str) -> list[str]:
    return [t for t in _goal_tokens(goal) if t not in _STOP and len(t) >= 3]


def _blob_contains(blob: str, phrases: tuple[str, ...]) -> bool:
    return any(p in blob for p in phrases)


def assess_readiness(
    packet: WorkspaceContextPacket,
    goal: str,
) -> list[Gap]:
    """
    Return gaps that should trigger the context HITL form.

    Empty list → main agent can start immediately.
    """
    goal = (goal or "").strip()
    goal_l = goal.lower()
    gaps: list[Gap] = []

    desc = (packet.identity.description or "").strip()
    confidence = (packet.meta.confidence or "low").lower()
    ready_docs = len(packet.evidence.documents_ready or [])
    external_ok = bool(packet.derived.tool_policy.external_context_ok)

    if confidence == "low" or not desc:
        gaps.append(
            Gap(
                id="thin_workspace",
                reason="Workspace has little framing (missing or thin description).",
                severity="high" if not desc else "medium",
            )
        )

    substantive = _substantive_tokens(goal)
    if len(goal) < 12 or len(substantive) < 2:
        gaps.append(
            Gap(
                id="vague_goal",
                reason="Goal is too short or lacks a concrete topic.",
                severity="high",
            )
        )

    if ready_docs == 0 and _blob_contains(goal_l, _DOC_IMPLIED):
        gaps.append(
            Gap(
                id="docs_implied",
                reason="Goal refers to personal documents but none are ready.",
                severity="high",
            )
        )

    if (
        ready_docs == 0
        and external_ok
        and _blob_contains(goal_l, _LEARN_OR_EXPLAIN)
    ):
        if len(substantive) < 4 or confidence in ("low", "medium"):
            gaps.append(
                Gap(
                    id="research_unscoped",
                    reason="Research goal needs scope (level, subtopics, sources).",
                    severity="medium",
                )
            )

    if _URL_REFERENCE.search(goal) and not _URL_IN_GOAL.search(goal):
        gaps.append(
            Gap(
                id="url_missing",
                reason="Goal refers to a link/article without a URL.",
                severity="high",
            )
        )

    audience = (packet.derived.audience_phrase or "").lower()
    audience_is_generic = audience in (
        "",
        "the workspace owner",
        "the workspace owner (self)",
    )
    if (
        _blob_contains(goal_l, _LEARN_OR_EXPLAIN)
        and audience_is_generic
        and not _blob_contains(goal_l, _AUDIENCE_HINTS)
        and confidence != "high"
    ):
        gaps.append(
            Gap(
                id="audience_unknown",
                reason="Audience is unclear for a teaching/explanatory goal.",
                severity="low",
            )
        )

    seen: set[str] = set()
    unique: list[Gap] = []
    for g in gaps:
        if g.id in seen:
            continue
        seen.add(g.id)
        unique.append(g)
    return unique
