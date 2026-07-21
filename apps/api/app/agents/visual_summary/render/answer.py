"""Resolve and size-limit main-agent narrative for presentation handoff."""

from __future__ import annotations

from typing import Any

PRESENTATION_ANSWER_MAX_CHARS = 32_000

_PLACEHOLDER_ANSWERS = frozenset(
    {
        "",
        "(no final answer)",
    }
)


def _step_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output.strip()
    return ""


def resolve_presentation_answer(
    *,
    final_answer: str | None,
    steps: list[Any] | None,
) -> str:
    """
    Pick the fullest substantive narrative from the completed main-agent run.
    Prefer the longest final/synthesis step output when it exceeds run.final_answer.
    """
    candidates: list[str] = []
    base = (final_answer or "").strip()
    if base and base not in _PLACEHOLDER_ANSWERS and not base.startswith(
        "Waiting for your approval"
    ):
        candidates.append(base)

    for step in sorted(steps or [], key=lambda s: getattr(s, "step_index", 0)):
        step_type = getattr(step, "type", None)
        if step_type not in ("final", "synthesis"):
            continue
        text = _step_output_text(getattr(step, "output", None))
        if text and len(text) > 40:
            candidates.append(text)

    if not candidates:
        return base
    return max(candidates, key=len)


def clip_presentation_answer(
    text: str,
    *,
    max_chars: int = PRESENTATION_ANSWER_MAX_CHARS,
) -> tuple[str, bool]:
    """Clip long answers at a paragraph boundary when possible."""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned, False

    clipped = cleaned[:max_chars]
    boundary = max(clipped.rfind("\n\n"), clipped.rfind("\n"))
    if boundary > max_chars // 2:
        clipped = clipped[:boundary].rstrip()
    return f"{clipped}\n\n[Answer truncated for model context.]", True