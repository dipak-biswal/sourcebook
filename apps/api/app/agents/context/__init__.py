"""Workspace Context Agent — always-on plan HITL + workspace merge + curator.

Flow: Run agent → plan follow-up questions (cheap LLM) → user answers →
optional write into empty workspace Settings fields → prompt curator builds
main-agent brief → main tool loop (date/web/docs/…) as usual.

Collects missing run context (topic, audience, URLs, document plan) via a
structured form when the workspace packet + goal are not enough, then frames
a COLLECTED RUN CONTEXT block for the main agent.
"""

from app.agents.context.merge import (
    CollectedContextSnapshot,
    answers_to_snapshot,
    format_collected_context,
)
from app.agents.context.phase import (
    CONTEXT_TOOL,
    is_questions_pending,
    resume_after_context_answers,
    start_context_phase_if_needed,
)
from app.agents.context.readiness import Gap, assess_readiness

__all__ = [
    "CONTEXT_TOOL",
    "CollectedContextSnapshot",
    "Gap",
    "answers_to_snapshot",
    "assess_readiness",
    "format_collected_context",
    "is_questions_pending",
    "resume_after_context_answers",
    "start_context_phase_if_needed",
]
