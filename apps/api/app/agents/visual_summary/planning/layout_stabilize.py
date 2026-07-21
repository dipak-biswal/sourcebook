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

from app.agents.visual_summary.planning.ui_intent import (
    _goal_lead_affordance,
    _interaction_sequence_has_data,
    _process_flow_has_data,
    available_source_hints,
    structured_field_present,
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


# Explain / learn visuals teach a process interactively — not a generic
# digest of every extractable field (key_points, FAQ, steps, chips, …).
# Domain-agnostic: any subject the user wants to learn.
_MECHANISM_ALLOWED_TYPES = frozenset(
    {
        "summary",
        "flow_diagram",
        "sequence_diagram",
        "key_terms",  # optional glossary only when concepts exist
    }
)
_MECHANISM_ALLOWED_HINTS = frozenset(
    {
        "summary",
        "process_flow",
        "interaction_sequence",
        "concepts",
    }
)
_MECHANISM_HINT_ORDER = (
    "summary",
    "process_flow",
    "interaction_sequence",
    "concepts",
)
_MECHANISM_DEFAULTS: dict[str, dict[str, Any]] = {
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
    "concepts": {
        "type": "key_terms",
        "title": "Core concepts",
        "purpose": "Terms to remember",
        "source_hint": "concepts",
        "width": "full",
    },
}


def _mechanism_teaching_outline(
    outline: list[dict[str, Any]],
    structured: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Keep only teaching blocks for explain goals:
    overview → how-it-works flow → worked-example sequence → optional glossary.

    Drops key_points, FAQ, steps, chips, callout, tables, etc. even if the
    extractor filled them — those belong to other presentation modes.
    """
    present = available_source_hints(structured)
    llm_by_hint = {_hint_key(e): e for e in outline if _hint_key(e)}
    ordered: list[dict[str, Any]] = []

    for hint in _MECHANISM_HINT_ORDER:
        if hint == "concepts":
            # Only real glossary fields — not key_points reused as concept_glossary.
            if not structured_field_present(structured, "concepts", "terms"):
                continue
            if "process_flow" not in present and "interaction_sequence" not in present:
                continue
        elif hint not in present:
            continue
        base = dict(_MECHANISM_DEFAULTS[hint])
        llm = llm_by_hint.get(hint)
        if llm:
            if llm.get("title"):
                base["title"] = llm["title"]
            if llm.get("purpose"):
                base["purpose"] = llm["purpose"]
            if llm.get("width"):
                base["width"] = llm["width"]
        ordered.append(base)

    # If extract failed entirely, still surface any allowed types from outline
    if not ordered:
        for e in outline:
            btype = str(e.get("type") or "")
            hint = _hint_key(e)
            if btype in _MECHANISM_ALLOWED_TYPES or hint in _MECHANISM_ALLOWED_HINTS:
                ordered.append(dict(e))
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
    - For explain/mechanism goals: teaching-only outline (no FAQ/steps/key_points)
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
        outline = _mechanism_teaching_outline(outline, structured)
        out["presentation_profile"] = sanitize_presentation_profile(
            "mechanism_explainer",
            goal=goal,
            fallback="mechanism_explainer",
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


# Abstract "controller" labels that often become star hubs and hide the real
# learning components (domain-agnostic — not tied to any subject).
_ABSTRACT_HUB_LABELS = frozenset(
    {
        "controller",
        "orchestrator",
        "coordinator",
        "manager",
        "system",
        "main",
        "core",
        "engine",
        "runtime",
        "loop",
        "event_loop",
        "event loop",
        "kernel",
        "brain",
    }
)


def _drop_hub_controller(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop a pure star hub so the diagram shows real handoffs between parts."""
    ids = {str(n.get("id") or "").strip() for n in nodes if str(n.get("id") or "").strip()}
    indeg = {i: 0 for i in ids}
    outdeg = {i: 0 for i in ids}
    for e in edges:
        s, t = str(e.get("source") or "").strip(), str(e.get("target") or "").strip()
        if s in ids and t in ids:
            outdeg[s] = outdeg.get(s, 0) + 1
            indeg[t] = indeg.get(t, 0) + 1

    hubs: list[str] = []
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        label = str(n.get("label") or "").strip().lower()
        slug = nid.lower().replace("-", "_")
        if not nid:
            continue
        abstract = (
            label in _ABSTRACT_HUB_LABELS
            or slug in _ABSTRACT_HUB_LABELS
            or any(a in label for a in ("controller", "orchestrator", "coordinator"))
        )
        if indeg.get(nid, 0) == 0 and outdeg.get(nid, 0) >= 3:
            hubs.append(nid)
        elif indeg.get(nid, 0) == 0 and outdeg.get(nid, 0) >= 2 and abstract:
            hubs.append(nid)

    if len(hubs) != 1:
        return nodes, edges
    hub = hubs[0]
    remaining_nodes = [n for n in nodes if str(n.get("id") or "").strip() != hub]
    rem_ids = {str(n.get("id") or "").strip() for n in remaining_nodes}
    remaining_edges = [
        e
        for e in edges
        if str(e.get("source") or "").strip() in rem_ids
        and str(e.get("target") or "").strip() in rem_ids
    ]
    if len(remaining_nodes) < 2 or not remaining_edges:
        return nodes, edges
    return remaining_nodes, remaining_edges


def _topo_sort_nodes(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Stable topological order so frontend columns don't reshuffle."""
    id_order = [str(n.get("id") or "").strip() for n in nodes if str(n.get("id") or "").strip()]
    by_id = {
        str(n.get("id") or "").strip(): n
        for n in nodes
        if str(n.get("id") or "").strip()
    }
    ids = set(id_order)
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        s, t = str(e.get("source") or "").strip(), str(e.get("target") or "").strip()
        if s in ids and t in ids and s != t:
            adj[s].append(t)
            indeg[t] = indeg.get(t, 0) + 1
    # Preserve original relative order among ties
    ready = [i for i in id_order if indeg.get(i, 0) == 0]
    out_ids: list[str] = []
    seen: set[str] = set()
    while ready:
        cur = ready.pop(0)
        if cur in seen:
            continue
        seen.add(cur)
        out_ids.append(cur)
        for nxt in adj.get(cur, []):
            indeg[nxt] = indeg.get(nxt, 0) - 1
            if indeg[nxt] == 0 and nxt not in seen:
                ready.append(nxt)
    for i in id_order:
        if i not in seen:
            out_ids.append(i)
    return [by_id[i] for i in out_ids if i in by_id]


def _stabilize_interaction_sequence(
    structured: dict[str, Any],
) -> dict[str, Any]:
    """Sort messages; prefer actors that match process_flow node labels/ids."""
    seq = structured.get("interaction_sequence")
    if not isinstance(seq, dict):
        return structured
    messages = [m for m in (seq.get("messages") or []) if isinstance(m, dict)]
    if not messages:
        return structured
    messages = sorted(
        messages,
        key=lambda m: (
            int(m.get("order")) if str(m.get("order", "")).lstrip("-").isdigit() else 0,
            str(m.get("label") or ""),
        ),
    )
    for i, m in enumerate(messages):
        m["order"] = i
        if not str(m.get("note") or "").strip():
            # Light teaching note so walkthrough panels aren't empty
            label = str(m.get("label") or "").strip()
            if label:
                m["note"] = f"At this step: {label}"

    actors = [str(a).strip() for a in (seq.get("actors") or []) if str(a).strip()]
    # Prefer flow node order when present
    pf = structured.get("process_flow")
    if isinstance(pf, dict):
        flow_labels = [
            str(n.get("label") or n.get("id") or "").strip()
            for n in (pf.get("nodes") or [])
            if isinstance(n, dict)
        ]
        flow_labels = [x for x in flow_labels if x]
        if flow_labels:
            # actors that appear in messages, ordered by flow then remainder
            used: set[str] = set()
            ordered_actors: list[str] = []
            msg_names = set()
            for m in messages:
                msg_names.add(str(m.get("source") or "").strip())
                msg_names.add(str(m.get("target") or "").strip())
            msg_names.discard("")
            for lab in flow_labels:
                # fuzzy: match actor that equals label or id slug
                for a in list(msg_names):
                    if a.lower() == lab.lower() or a.lower().replace(" ", "_") == lab.lower().replace(
                        " ", "_"
                    ):
                        if a not in used:
                            ordered_actors.append(a)
                            used.add(a)
            for a in actors:
                if a not in used and a in msg_names:
                    ordered_actors.append(a)
                    used.add(a)
            for a in msg_names:
                if a not in used:
                    ordered_actors.append(a)
                    used.add(a)
            if len(ordered_actors) >= 2:
                actors = ordered_actors

    out = dict(structured)
    out["interaction_sequence"] = {"actors": actors[:8], "messages": messages[:24]}
    return out


def stabilize_process_flow_topology(
    structured: dict[str, Any],
    *,
    goal: str = "",
) -> dict[str, Any]:
    """
    Domain-agnostic teaching cleanup for process_flow (+ sequence polish):

    1. Drop abstract hub-only controller nodes (star graphs hide real parts)
    2. Topological node order for consistent frontend columns
    3. Ensure each node has a short teaching detail
    4. Sort / annotate interaction_sequence for step walkthroughs

    Does **not** hardcode any subject (JS, biology, finance, …) — node labels
    and edges come from the answer/extract; we only stabilize structure.
    """
    del goal  # reserved for future goal-aware (still domain-agnostic) polish
    if not isinstance(structured, dict):
        return structured
    out = dict(structured)
    pf = out.get("process_flow")
    if isinstance(pf, dict):
        nodes = [n for n in (pf.get("nodes") or []) if isinstance(n, dict)]
        edges = [e for e in (pf.get("edges") or []) if isinstance(e, dict)]
        if len(nodes) >= 2:
            nodes, edges = _drop_hub_controller(nodes, edges)
            nodes = _topo_sort_nodes(nodes, edges)
            for n in nodes:
                if not str(n.get("detail") or "").strip():
                    label = str(n.get("label") or n.get("id") or "Part").strip()
                    n["detail"] = f"What {label} does in this process."
            out["process_flow"] = {"nodes": nodes, "edges": edges}

    out = _stabilize_interaction_sequence(out)
    return out
