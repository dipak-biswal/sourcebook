"""Phase B — code validation for layout plans before render_ui."""

from __future__ import annotations

import json
import re
from typing import Any

from app.presentation.layout import layout_components_from_goal
from app.presentation.ui_intent import KNOWN_SOURCE_HINTS, available_source_hints

ALLOWED_BLOCK_TYPES = frozenset(
    {
        "summary",
        "key_points",
        "faq",
        "key_terms",
        "table",
        "progress",
        "chart",
        "chips",
        "callout",
        "steps",
        "timeline",
        "comparison",
        "quote",
        "metrics",
    }
)

_VALID_WIDTHS = frozenset({"full", "half"})
_DATE_RE = re.compile(r"\b(19|20)\d{2}\b")


def _structured_has_content(structured: dict[str, Any]) -> bool:
    if (structured.get("summary") or "").strip():
        return True
    if structured.get("key_points"):
        return True
    if structured.get("faq"):
        return True
    if structured.get("sections"):
        return True
    return False


def _has_dates_in_facts(structured: dict[str, Any], final_answer: str = "") -> bool:
    blob = json.dumps(structured, ensure_ascii=False, default=str) + (final_answer or "")
    return bool(_DATE_RE.search(blob))


def _has_skill_labels(structured: dict[str, Any]) -> bool:
    if structured.get("key_points"):
        return True
    for section in structured.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if section.get("bullets"):
            return True
        body = str(section.get("body") or "")
        if "|" in body or re.search(r"\b(skill|level|gap|strong|growing)\b", body, re.I):
            return True
    summary = str(structured.get("summary") or "")
    return bool(re.search(r"\b(skill|experience|proficien|stack)\b", summary, re.I))


def _outline_block_types(plan: dict[str, Any]) -> list[str]:
    types: list[str] = []
    for block in plan.get("block_outline") or []:
        if isinstance(block, dict) and block.get("type"):
            types.append(str(block["type"]))
    return types


def validate_layout_plan(
    plan: dict[str, Any],
    *,
    goal: str,
    structured_content: dict[str, Any],
    requested_components: list[str] | None = None,
    final_answer: str = "",
) -> tuple[bool, list[str]]:
    """
    Validate a layout plan against goal components and structured facts.

    Returns (ok, errors).
    """
    if not isinstance(plan, dict):
        return False, ["layout_plan must be a JSON object"]

    errors: list[str] = []
    components = list(plan.get("components") or [])
    outline_types = _outline_block_types(plan)
    combined_types = set(components) | set(outline_types)
    profile = str(plan.get("presentation_profile") or "").strip()
    skeleton_mode = profile == "workspace_derived" or any(
        isinstance(b, dict) and b.get("source_hint") for b in (plan.get("block_outline") or [])
    )
    goal_components = (
        []
        if skeleton_mode
        else (requested_components or layout_components_from_goal(goal))
    )

    if not profile:
        errors.append("presentation_profile is required")

    present_hints = available_source_hints(
        structured_content if isinstance(structured_content, dict) else {}
    )
    known_hints = frozenset(KNOWN_SOURCE_HINTS)
    # When any entry already carries source_hint (skeleton / LLM-authority plans),
    # require every entry to be grounded. Legacy plans without source_hints still pass.
    outline_entries = [
        b for b in (plan.get("block_outline") or []) if isinstance(b, dict)
    ]
    require_source_hints = any(b.get("source_hint") for b in outline_entries) or (
        profile == "workspace_derived" and bool(outline_entries)
    )

    for block in plan.get("block_outline") or []:
        if not isinstance(block, dict):
            errors.append("block_outline entries must be objects")
            continue
        btype = str(block.get("type") or "").strip()
        if not btype:
            errors.append("Each block_outline entry needs a type")
            continue
        if btype not in ALLOWED_BLOCK_TYPES:
            errors.append(f"Unsupported block type: {btype}")

        # Width: invalid values are non-fatal — drop so assembly uses defaults.
        width = block.get("width")
        if width is not None and str(width).strip() and str(width).strip() not in _VALID_WIDTHS:
            block.pop("width", None)

        hint = str(block.get("source_hint") or "").strip()
        if require_source_hints and not hint:
            errors.append(
                f"block_outline entry type={btype!r} is missing required source_hint"
            )
            continue
        if not hint:
            continue
        if hint not in known_hints:
            errors.append(
                f"Unknown source_hint {hint!r} on block type={btype!r} "
                f"(allowed: {', '.join(KNOWN_SOURCE_HINTS)})"
            )
            continue
        if hint not in present_hints:
            errors.append(
                f"source_hint {hint!r} has no data in structured_content "
                f"(block type={btype!r})"
            )

    if _structured_has_content(structured_content) and not outline_types:
        errors.append(
            "block_outline is empty but structured content exists — plan at least one block"
        )

    # Goal regex components only enforced for legacy LLM plans (not skeleton)
    for required in goal_components:
        if required not in combined_types:
            errors.append(
                f"Requested component '{required}' from goal is missing in "
                "components or block_outline"
            )

    if "timeline" in combined_types and not _has_dates_in_facts(
        structured_content, final_answer
    ):
        errors.append(
            "timeline block planned but no dates/years found in structured content"
        )

    if (
        not skeleton_mode
        and "progress" in combined_types
        and not _has_skill_labels(structured_content)
    ):
        errors.append(
            "progress block planned but no skill labels or key_points in structured content"
        )

    return (len(errors) == 0, errors)


def format_validator_notes(errors: list[str]) -> str:
    """Planner notes payload for a single auto-replan attempt."""
    lines = ["LAYOUT PLAN VALIDATION FAILED — fix these issues:"]
    lines.extend(f"- {err}" for err in errors)
    lines.append("Return a revised layout JSON that satisfies every item above.")
    return "\n".join(lines)