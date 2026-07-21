"""Stabilize layout plans so the same goal does not produce random Visual UIs.

LLM extract+plan is free-form; without post-processing we get:
- presentation_profile = literal "short_snake_case"
- different process_flow topologies every run
- missing flow/sequence blocks even when data exists
- block order that ignores the mechanism-first skeleton

This module is pure code (no LLM). Call it after planning, before assembly.
"""

from __future__ import annotations

import re
from typing import Any

from app.presentation.ui_intent import (
    _goal_lead_affordance,
    _interaction_sequence_has_data,
    _process_flow_has_data,
    available_source_hints,
)

# Profiles models copy from few-shots / prompt templates by mistake.
_PLACEHOLDER_PROFILES = frozenset(
    {
        "short_snake_case",
        "short snake case",
        "snake_case",
        "snake case",
        "e.g. gap_analysis",
        "eg gap_analysis",
        "example",
        "profile",
        "presentation_profile",
    }
)

_PROFILE_SLUG_RE = re.compile(r"[^a-z0-9]+")


def sanitize_presentation_profile(
    profile: str | None,
    *,
    goal: str = "",
    fallback: str = "workspace_derived",
) -> str:
    """Return a usable snake_case profile; replace placeholders."""
    raw = str(profile or "").strip()
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    lowered = _PROFILE_SLUG_RE.sub("_", lowered).strip("_")
    if not lowered or lowered in _PLACEHOLDER_PROFILES or lowered in {
        "short_snake_case",
        "snake_case",
    }:
        lead = _goal_lead_affordance(goal or "")
        if lead == "mechanism_explainer":
            return "mechanism_explainer"
        if lead == "comparison_matrix":
            return "gap_analysis"
        if lead == "ordered_guide":
            return "how_to_guide"
        if lead == "timeline":
            return "timeline"
        return fallback[:60] if fallback else "workspace_derived"
    # Collapse accidental "short_snake_case_e_g_gap_analysis"
    if "short_snake" in lowered or lowered.startswith("e_g_"):
        lead = _goal_lead_affordance(goal or "")
        if lead == "mechanism_explainer":
            return "mechanism_explainer"
        return fallback[:60] if fallback else "workspace_derived"
    return lowered[:60]


def _outline_entries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = plan.get("block_outline") or []
    return [b for b in raw if isinstance(b, dict) and b.get("type")]


def _hint_key(entry: dict[str, Any]) -> str:
    return str(entry.get("source_hint") or "").strip()


def _ensure_diagram_entries(
    outline: list[dict[str, Any]],
    structured: dict[str, Any],
    *,
    goal: str,
) -> list[dict[str, Any]]:
    """Inject flow/sequence outline rows when structured data exists but plan omitted them."""
    present = available_source_hints(structured)
    by_hint = {_hint_key(e): e for e in outline if _hint_key(e)}
    out = list(outline)

    def insert_after_summary(entry: dict[str, Any]) -> None:
        # Prefer right after first summary; else at front of outline.
        idx = 0
        for i, e in enumerate(out):
            if str(e.get("type") or "") == "summary":
                idx = i + 1
                break
        out.insert(idx, entry)

    is_mechanism = _goal_lead_affordance(goal) == "mechanism_explainer"

    if "process_flow" in present and "process_flow" not in by_hint:
        entry = {
            "type": "flow_diagram",
            "title": "How it works",
            "purpose": "Architecture: components and handoffs",
            "source_hint": "process_flow",
            "width": "full",
            "affordance": "mechanism_explainer",
        }
        if is_mechanism:
            insert_after_summary(entry)
        else:
            out.append(entry)
        by_hint["process_flow"] = entry

    if "interaction_sequence" in present and "interaction_sequence" not in by_hint:
        entry = {
            "type": "sequence_diagram",
            "title": "Worked example",
            "purpose": "Step-by-step walkthrough of one concrete run",
            "source_hint": "interaction_sequence",
            "width": "full",
            "affordance": "interaction_walkthrough",
        }
        # Place after flow when present
        if "process_flow" in by_hint:
            for i, e in enumerate(out):
                if _hint_key(e) == "process_flow":
                    out.insert(i + 1, entry)
                    break
            else:
                out.append(entry)
        elif is_mechanism:
            insert_after_summary(entry)
        else:
            out.append(entry)

    return out


def _mechanism_block_order(
    outline: list[dict[str, Any]],
    skeleton_outline: list[dict[str, Any]] | None,
    structured: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Stable order for mechanism UIs:
    summary → flow_diagram → sequence_diagram → rest (skeleton order, then leftover).
    Prefer skeleton titles/order when the same source_hint exists.
    """
    llm_by_hint = {_hint_key(e): e for e in outline if _hint_key(e)}
    sk_list = [
        e
        for e in (skeleton_outline or [])
        if isinstance(e, dict) and e.get("type") and _hint_key(e)
    ]
    present = available_source_hints(structured)

    # Overlay: skeleton structure + LLM title/purpose when both have the hint.
    ordered: list[dict[str, Any]] = []
    seen_hints: set[str] = set()

    def take(entry: dict[str, Any]) -> None:
        hint = _hint_key(entry)
        if hint and hint in seen_hints:
            return
        if hint and hint not in present and hint not in (
            # free-form blocks without structured data
        ):
            # Only skip grounded hints that have no data
            if hint in {
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
                "process_flow",
                "interaction_sequence",
            }:
                if hint not in present:
                    return
        llm = llm_by_hint.get(hint) if hint else None
        merged = dict(entry)
        if llm:
            if llm.get("title"):
                merged["title"] = llm["title"]
            if llm.get("purpose"):
                merged["purpose"] = llm["purpose"]
            if llm.get("width"):
                merged["width"] = llm["width"]
        ordered.append(merged)
        if hint:
            seen_hints.add(hint)

    # Phase 1: fixed hero order when data exists
    hero_hints = ("summary", "process_flow", "interaction_sequence")
    hero_defaults = {
        "summary": {
            "type": "summary",
            "title": "Overview",
            "purpose": "What this is in plain language",
            "source_hint": "summary",
            "width": "full",
        },
        "process_flow": {
            "type": "flow_diagram",
            "title": "How it works",
            "purpose": "Architecture: components and handoffs",
            "source_hint": "process_flow",
            "width": "full",
        },
        "interaction_sequence": {
            "type": "sequence_diagram",
            "title": "Worked example",
            "purpose": "Step-by-step walkthrough of one concrete run",
            "source_hint": "interaction_sequence",
            "width": "full",
        },
    }
    for hint in hero_hints:
        if hint not in present:
            continue
        base = next((e for e in sk_list if _hint_key(e) == hint), None)
        if base is None:
            base = llm_by_hint.get(hint) or hero_defaults[hint]
        take(base)

    # Phase 2: remaining skeleton entries (stable)
    for e in sk_list:
        take(e)

    # Phase 3: any LLM-only entries still grounded
    for e in outline:
        take(e)

    return ordered


def stabilize_layout_plan(
    plan: dict[str, Any] | None,
    *,
    structured: dict[str, Any] | None = None,
    skeleton_plan: dict[str, Any] | None = None,
    goal: str = "",
) -> dict[str, Any]:
    """
    Normalize a layout plan for stable visual summaries.

    - Sanitize presentation_profile placeholders
    - Inject flow/sequence blocks when structured data exists
    - For explain/mechanism goals: fixed hero order + skeleton-first remaining order
    """
    if not isinstance(plan, dict):
        plan = {}
    structured = structured if isinstance(structured, dict) else {}
    skeleton_plan = skeleton_plan if isinstance(skeleton_plan, dict) else {}

    out = dict(plan)
    out["presentation_profile"] = sanitize_presentation_profile(
        out.get("presentation_profile"),
        goal=goal,
        fallback=str(skeleton_plan.get("presentation_profile") or "workspace_derived"),
    )

    outline = _outline_entries(out)
    outline = _ensure_diagram_entries(outline, structured, goal=goal)

    lead = _goal_lead_affordance(goal)
    has_mechanism_data = _process_flow_has_data(structured) or _interaction_sequence_has_data(
        structured
    )
    if lead == "mechanism_explainer" and has_mechanism_data:
        outline = _mechanism_block_order(
            outline,
            _outline_entries(skeleton_plan),
            structured,
        )

    out["block_outline"] = outline
    # Keep components in sync with outline types
    types: list[str] = []
    for e in outline:
        t = str(e.get("type") or "").strip()
        if t and t not in types:
            types.append(t)
    if types:
        out["components"] = types
    return out


def stabilize_process_flow_topology(structured: dict[str, Any]) -> dict[str, Any]:
    """
    Light cleanup of process_flow graphs that invent a hub 'controller' node
    with only outgoing edges and no incoming handoffs (common random pattern).

    Does not invent new steps — only drops a hub-only node when remaining graph
    still has ≥2 nodes and ≥1 edge. Safe no-op otherwise.
    """
    if not isinstance(structured, dict):
        return structured
    pf = structured.get("process_flow")
    if not isinstance(pf, dict):
        return structured
    nodes = [n for n in (pf.get("nodes") or []) if isinstance(n, dict)]
    edges = [e for e in (pf.get("edges") or []) if isinstance(e, dict)]
    if len(nodes) < 3 or len(edges) < 2:
        return structured

    ids = {str(n.get("id") or "").strip() for n in nodes if str(n.get("id") or "").strip()}
    indeg = {i: 0 for i in ids}
    outdeg = {i: 0 for i in ids}
    for e in edges:
        s, t = str(e.get("source") or "").strip(), str(e.get("target") or "").strip()
        if s in ids and t in ids:
            outdeg[s] = outdeg.get(s, 0) + 1
            indeg[t] = indeg.get(t, 0) + 1

    # Hub: in=0, out>=3, or label looks like the abstract controller
    hubs = []
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        label = str(n.get("label") or "").strip().lower()
        if not nid:
            continue
        if indeg.get(nid, 0) == 0 and outdeg.get(nid, 0) >= 3:
            hubs.append(nid)
        elif indeg.get(nid, 0) == 0 and outdeg.get(nid, 0) >= 2 and (
            "event loop" in label or nid in ("event_loop", "controller", "orchestrator")
        ):
            hubs.append(nid)

    if len(hubs) != 1:
        return structured
    hub = hubs[0]
    remaining_nodes = [n for n in nodes if str(n.get("id") or "").strip() != hub]
    remaining_edges = [
        e
        for e in edges
        if str(e.get("source") or "").strip() != hub
        and str(e.get("target") or "").strip() != hub
    ]
    rem_ids = {str(n.get("id") or "").strip() for n in remaining_nodes}
    remaining_edges = [
        e
        for e in remaining_edges
        if str(e.get("source") or "").strip() in rem_ids
        and str(e.get("target") or "").strip() in rem_ids
    ]
    if len(remaining_nodes) < 2 or not remaining_edges:
        return structured

    out = dict(structured)
    out["process_flow"] = {"nodes": remaining_nodes, "edges": remaining_edges}
    return out
