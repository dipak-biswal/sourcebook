"""UiIntent: affordance ∩ data → skeleton layout (no vertical hardcoding)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.presentation.layout import layout_components_from_goal

# Affordance → (block_type, source_hint, default_title)
_AFFORDANCE_SPEC: dict[str, tuple[str, str, str]] = {
    "overview": ("summary", "summary", "Overview"),
    "highlights": ("key_points", "key_points", "Key points"),
    "concept_glossary": ("key_terms", "concepts", "Core concepts"),
    "ordered_guide": ("steps", "ordered_actions", "Steps"),
    "comparison_matrix": ("table", "matrix_rows", "Comparison"),
    "qualitative_levels": ("progress", "levels", "Levels"),
    "self_check": ("faq", "faq", "FAQ"),
    "priority_alert": ("callout", "priority_message", "Priority"),
    "topic_filter": ("chips", "themes", "Themes"),
    "timeline": ("timeline", "milestones", "Timeline"),
    "metrics": ("metrics", "metrics", "Metrics"),
}

# Secondary block when primary data shape fits comparison better as comparison type
_COMPARISON_ALT = ("comparison", "comparisons", "Tradeoffs")

_DEFAULT_AFFORDANCE_ORDER = (
    "overview",
    "priority_alert",
    "topic_filter",
    "concept_glossary",
    "highlights",
    "comparison_matrix",
    "qualitative_levels",
    "ordered_guide",
    "metrics",
    "timeline",
    "self_check",
)

_DATE_RE = re.compile(r"\b(19|20)\d{2}\b")

# Goal phrasing → the affordance that should lead the layout when it has data.
# Lets a "compare X vs Y" or "how do I…" goal open on its most useful block
# instead of every summary starting with a generic Overview.
_GOAL_LEAD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(compare|comparison|versus|vs\.?|difference|differences|"
            r"trade[- ]?offs?|pros and cons)\b",
            re.I,
        ),
        "comparison_matrix",
    ),
    (
        re.compile(
            r"\b(how to|how do|how can|step[- ]?by[- ]?step|walkthrough|"
            r"set up|configure|install|implement)\b",
            re.I,
        ),
        "ordered_guide",
    ),
    (
        re.compile(
            r"\b(timeline|history|roadmap|milestones?|evolution|chronolog\w*|over time)\b",
            re.I,
        ),
        "timeline",
    ),
    (
        re.compile(
            r"\b(risk|risks|gaps?|blockers?|urgent|priorit\w+|what.?s wrong)\b",
            re.I,
        ),
        "priority_alert",
    ),
)


def _goal_lead_affordance(goal: str) -> str | None:
    text = goal or ""
    for pattern, affordance in _GOAL_LEAD_PATTERNS:
        if pattern.search(text):
            return affordance
    return None


@dataclass
class UiIntent:
    eligible_affordances: list[str] = field(default_factory=list)
    block_order: list[str] = field(default_factory=list)
    emphasis: str = ""
    exclude: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_affordances": list(self.eligible_affordances),
            "block_order": list(self.block_order),
            "emphasis": self.emphasis,
            "exclude": list(self.exclude),
            "scores": dict(self.scores),
        }


def _nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _nonempty_str(value: Any) -> bool:
    return bool(str(value or "").strip())


def structured_field_present(structured: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        val = structured.get(key)
        if _nonempty_str(val) or _nonempty_list(val):
            return True
    return False


def _sections_as_steps(structured: dict[str, Any]) -> bool:
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        bullets = sec.get("bullets") or []
        if isinstance(bullets, list) and len(bullets) >= 2:
            return True
        body = str(sec.get("body") or "")
        if re.search(r"^\s*\d+[.)]", body, re.M):
            return True
    return False


def _pipe_rows_present(structured: dict[str, Any]) -> bool:
    for key in ("key_points", "matrix_rows", "comparisons", "levels"):
        for item in structured.get(key) or []:
            if isinstance(item, str) and "|" in item:
                return True
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for b in sec.get("bullets") or []:
            if isinstance(b, str) and "|" in b:
                return True
        if "|" in str(sec.get("body") or ""):
            return True
    return False


def affordance_has_data(affordance: str, structured: dict[str, Any]) -> bool:
    """True when structured content can fill this affordance."""
    if affordance == "overview":
        return structured_field_present(structured, "summary") or structured_field_present(
            structured, "key_points"
        )
    if affordance == "highlights":
        return structured_field_present(structured, "key_points") or _sections_as_steps(
            structured
        )
    if affordance == "concept_glossary":
        return (
            structured_field_present(structured, "concepts", "terms")
            or structured_field_present(structured, "key_points")
        )
    if affordance == "ordered_guide":
        return (
            structured_field_present(
                structured, "ordered_actions", "learning_path", "design_process", "steps"
            )
            or _sections_as_steps(structured)
        )
    if affordance == "comparison_matrix":
        return (
            structured_field_present(structured, "matrix_rows", "comparisons")
            or _pipe_rows_present(structured)
        )
    if affordance == "qualitative_levels":
        if structured_field_present(structured, "levels"):
            return True
        for item in structured.get("key_points") or []:
            if isinstance(item, str) and "|" in item and re.search(
                r"strong|growing|gap|foundational|weak", item, re.I
            ):
                return True
        return False
    if affordance == "self_check":
        return structured_field_present(structured, "faq", "misconceptions")
    if affordance == "priority_alert":
        return (
            structured_field_present(structured, "priority_message", "gaps", "risks")
            or structured_field_present(structured, "summary")
        )
    if affordance == "topic_filter":
        themes = structured.get("themes") or []
        return isinstance(themes, list) and len(themes) >= 2
    if affordance == "timeline":
        if structured_field_present(structured, "milestones", "timeline"):
            return True
        blob = str(structured.get("summary") or "") + json_dumps_safe(structured)
        return bool(_DATE_RE.search(blob))
    if affordance == "metrics":
        return structured_field_present(structured, "metrics")
    return False


# source_hint → affordance used for data presence (mirrors assemble_block branches)
_SOURCE_HINT_AFFORDANCE: dict[str, str] = {
    "summary": "overview",
    "key_points": "highlights",
    "concepts": "concept_glossary",
    "ordered_actions": "ordered_guide",
    "matrix_rows": "comparison_matrix",
    "comparisons": "comparison_matrix",
    "levels": "qualitative_levels",
    "faq": "self_check",
    "priority_message": "priority_alert",
    "themes": "topic_filter",
    "milestones": "timeline",
    "metrics": "metrics",
}

# Canonical source_hints the planner may use (order is prompt display order).
KNOWN_SOURCE_HINTS: tuple[str, ...] = (
    "summary",
    "key_points",
    "concepts",
    "ordered_actions",
    "matrix_rows",
    "comparisons",
    "levels",
    "faq",
    "priority_message",
    "themes",
    "milestones",
    "metrics",
)


def available_source_hints(structured: dict[str, Any]) -> set[str]:
    """
    Return source_hint values that currently have fillable data.

    Used as the planner whitelist and by validate_layout_plan grounding checks.
    """
    structured = structured if isinstance(structured, dict) else {}
    present: set[str] = set()
    for hint in KNOWN_SOURCE_HINTS:
        if hint == "priority_message":
            # The callout assembler refuses to fabricate from the summary, so
            # only advertise this hint when real priority/gap/risk data exists.
            if structured_field_present(structured, "priority_message", "gaps", "risks"):
                present.add(hint)
            continue
        if hint == "comparisons":
            # Prefer real comparisons list; pipe rows also feed comparison blocks.
            if structured_field_present(structured, "comparisons") or _pipe_rows_present(
                structured
            ):
                present.add(hint)
            continue
        if hint == "matrix_rows":
            if structured_field_present(structured, "matrix_rows") or _pipe_rows_present(
                structured
            ):
                present.add(hint)
            continue
        aff = _SOURCE_HINT_AFFORDANCE.get(hint)
        if aff and affordance_has_data(aff, structured):
            present.add(hint)
    return present


def json_dumps_safe(obj: Any) -> str:
    try:
        import json

        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def _workspace_affordances(packet: dict[str, Any] | None) -> list[str]:
    if not isinstance(packet, dict):
        return ["overview", "highlights", "self_check"]
    derived = packet.get("derived") if isinstance(packet.get("derived"), dict) else {}
    raw = derived.get("visual_affordances") or packet.get("visual_affordances") or []
    out = [str(a).strip() for a in raw if str(a).strip()]
    return out or ["overview", "highlights", "self_check"]


def _workspace_rank(packet: dict[str, Any] | None, affordance: str) -> float:
    affs = _workspace_affordances(packet)
    if affordance not in affs:
        return 0.0
    # Earlier in packet list = higher priority
    idx = affs.index(affordance)
    return max(0.0, 10.0 - idx * 0.5)


def _hint_affordances(hints: dict[str, Any] | None) -> list[str]:
    if not isinstance(hints, dict):
        return []
    raw = hints.get("suggested_affordances") or []
    return [str(a).strip() for a in raw if str(a).strip()]


def _goal_boost(goal: str, affordance: str) -> float:
    components = layout_components_from_goal(goal or "")
    block = _AFFORDANCE_SPEC.get(affordance, ("", "", ""))[0]
    if block and block in components:
        return 1.5
    # map goal components to affordances
    mapping = {
        "table": "comparison_matrix",
        "progress": "qualitative_levels",
        "faq": "self_check",
        "chips": "topic_filter",
        "callout": "priority_alert",
        "timeline": "timeline",
        "key_points": "highlights",
        "key_terms": "concept_glossary",
        "comparison": "comparison_matrix",
        "steps": "ordered_guide",
    }
    for comp in components:
        if mapping.get(comp) == affordance:
            return 1.5
    return 0.0


def _data_richness(affordance: str, structured: dict[str, Any]) -> float:
    if affordance == "overview" and structured_field_present(structured, "summary"):
        return min(3.0, len(str(structured.get("summary") or "")) / 80.0)
    if affordance == "highlights":
        return float(min(5, len(structured.get("key_points") or [])))
    if affordance == "self_check":
        return float(min(5, len(structured.get("faq") or [])))
    if affordance == "topic_filter":
        return float(min(4, len(structured.get("themes") or [])))
    if affordance == "ordered_guide" and _sections_as_steps(structured):
        return 2.0
    if affordance == "comparison_matrix" and _pipe_rows_present(structured):
        return 2.0
    return 1.0 if affordance_has_data(affordance, structured) else 0.0


def resolve_ui_intent(
    *,
    structured_content: dict[str, Any],
    workspace_packet: dict[str, Any] | None = None,
    presentation_hints: dict[str, Any] | None = None,
    goal: str = "",
) -> UiIntent:
    """Merge packet affordances ∩ data ∩ hints; order by score."""
    structured = structured_content if isinstance(structured_content, dict) else {}
    candidates = set(_workspace_affordances(workspace_packet))
    candidates.update(_hint_affordances(presentation_hints))
    # Always consider overview/highlights/self_check if data exists
    for base in ("overview", "highlights", "self_check", "topic_filter", "ordered_guide"):
        candidates.add(base)

    scores: dict[str, float] = {}
    eligible: list[str] = []
    for aff in candidates:
        if aff not in _AFFORDANCE_SPEC:
            continue
        if not affordance_has_data(aff, structured):
            continue
        score = (
            _workspace_rank(workspace_packet, aff)
            + (2.0 if aff in _hint_affordances(presentation_hints) else 0.0)
            + _goal_boost(goal, aff)
            + _data_richness(aff, structured)
        )
        scores[aff] = score
        eligible.append(aff)

    # Stable order: score desc, then default order
    def sort_key(a: str) -> tuple[float, int]:
        try:
            default_idx = _DEFAULT_AFFORDANCE_ORDER.index(a)
        except ValueError:
            default_idx = 99
        return (-scores.get(a, 0.0), default_idx)

    ordered = sorted(eligible, key=sort_key)
    # Lead with the goal-implied affordance (compare/how-to/timeline/priority)
    # when it has data; otherwise open on the scannable Overview.
    lead = _goal_lead_affordance(goal)
    if lead and lead in ordered:
        ordered = [lead] + [a for a in ordered if a != lead]
    elif "overview" in ordered:
        ordered = ["overview"] + [a for a in ordered if a != "overview"]
    # Cap outline size for scannability
    block_order = ordered[:8]

    emphasis = ""
    if isinstance(presentation_hints, dict):
        emphasis = str(presentation_hints.get("emphasis") or "").strip()
    if not emphasis and isinstance(workspace_packet, dict):
        derived = workspace_packet.get("derived") or {}
        if isinstance(derived, dict):
            emphasis = str(
                derived.get("success_criteria") or derived.get("outcome_phrase") or ""
            ).strip()[:200]

    all_known = set(_AFFORDANCE_SPEC)
    exclude = sorted(all_known - set(eligible))

    return UiIntent(
        eligible_affordances=sorted(eligible, key=sort_key),
        block_order=block_order,
        emphasis=emphasis,
        exclude=exclude,
        scores=scores,
    )


def build_skeleton_layout_plan(
    intent: UiIntent,
    *,
    structured_content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Code skeleton block_outline with source_hint — planner must not invent types."""
    structured = structured_content if isinstance(structured_content, dict) else {}
    outline: list[dict[str, str]] = []
    components: list[str] = []

    for aff in intent.block_order:
        spec = _AFFORDANCE_SPEC.get(aff)
        if not spec:
            continue
        btype, source_hint, title = spec
        # Prefer comparison block when comparisons list exists without matrix
        if aff == "comparison_matrix":
            if structured_field_present(structured, "comparisons") and not structured_field_present(
                structured, "matrix_rows"
            ):
                btype, source_hint, title = _COMPARISON_ALT
            elif not structured_field_present(structured, "matrix_rows", "comparisons"):
                # pipe rows in key_points → table
                source_hint = "matrix_rows"

        purpose = intent.emphasis or f"Present {title.lower()} from handoff"
        entry = {
            "type": btype,
            "title": title,
            "purpose": purpose[:200],
            "source_hint": source_hint,
            "affordance": aff,
        }
        outline.append(entry)
        if btype not in components:
            components.append(btype)

    if not outline and structured_field_present(structured, "summary", "key_points", "faq"):
        # Minimal digest
        if structured_field_present(structured, "summary"):
            outline.append(
                {
                    "type": "summary",
                    "title": "Overview",
                    "purpose": "Overview",
                    "source_hint": "summary",
                    "affordance": "overview",
                }
            )
            components.append("summary")
        if structured_field_present(structured, "key_points"):
            outline.append(
                {
                    "type": "key_points",
                    "title": "Key points",
                    "purpose": "Highlights",
                    "source_hint": "key_points",
                    "affordance": "highlights",
                }
            )
            components.append("key_points")

    return {
        "presentation_profile": "workspace_derived",
        "components": components,
        "block_outline": outline,
        "rationale": (
            f"Skeleton from UiIntent ({len(outline)} blocks). "
            f"Emphasis: {intent.emphasis or 'n/a'}"
        ),
        "ui_intent": intent.to_dict(),
    }
