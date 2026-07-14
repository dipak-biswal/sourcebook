"""Decide when agent runs get an automatic generative UI attachment."""

from __future__ import annotations

import re

# Operational goals — text-only agent result is enough.
_SKIP_GOAL = re.compile(
    r"(?i)^\s*(?:"
    r"create\s+a?\s*note|"
    r"list\s+documents?|"
    r"delete|"
    r"approve|"
    r"reject"
    r")\b",
)

# Explanatory / analytical goals — worth a rich layout.
_PRESENT_GOAL = re.compile(
    r"(?i)\b(?:"
    r"explain|summar(?:y|ize)|teach|overview|describe|"
    r"compare|contrast|review|analyze|analyse|"
    r"improve|tailor|help\s+me\s+understand|"
    r"key\s+points?|faq|glossary|study|learn|"
    r"how\s+does|what\s+is|walk\s+me\s+through|"
    r"visualize|break\s+down|outline"
    r")\b",
)

_MIN_ANSWER_CHARS = 80


def should_render_presentation(
    *,
    goal: str,
    final_answer: str | None,
    status: str,
) -> bool:
    """
    Profile-agnostic gate: no workspace enum required.
    Returns True when an agent run likely benefits from generative UI.
    """
    if status != "completed":
        return False

    goal = (goal or "").strip()
    answer = (final_answer or "").strip()

    if not goal or not answer:
        return False
    if answer in ("(no final answer)",):
        return False
    if len(answer) < _MIN_ANSWER_CHARS and not _PRESENT_GOAL.search(goal):
        return False
    if _SKIP_GOAL.search(goal):
        return False

    return bool(_PRESENT_GOAL.search(goal) or len(answer) >= 200)


def should_offer_presentation(
    *,
    goal: str,
    final_answer: str | None,
    status: str,
) -> bool:
    """
    Human-in-the-loop gate: offer generative UI after most substantive answers.
    Broader than should_render_presentation — user opts in before we build.
    """
    if status != "completed":
        return False

    goal = (goal or "").strip()
    answer = (final_answer or "").strip()

    if not goal or not answer:
        return False
    if answer in ("(no final answer)",):
        return False
    if answer.startswith("Waiting for your approval"):
        return False
    if len(answer) < 40:
        return False
    if _SKIP_GOAL.search(goal):
        return False

    return True