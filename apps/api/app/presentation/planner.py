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

def should_offer_presentation(
    *,
    goal: str,
    final_answer: str | None,
    status: str,
) -> bool:
    """Human-in-the-loop gate: offer generative UI after most substantive answers."""
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