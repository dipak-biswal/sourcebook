"""LLM workspace profiler — domain-agnostic context derivation, cached per workspace.

The keyword heuristic in workspace_context.py only recognizes career/study
vocabulary; any other workspace (recipes, contracts, training plans, …) falls
through to a generic layout. This module derives the same WorkspaceDerived
schema with one LLM call — plus a domain label and a planner few-shot example
shaped for the workspace — and caches the result on workspaces.context_cache,
keyed by a fingerprint of the inputs. The heuristic packet stays as base and
fallback, so a missing key or failed call never degrades below today.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Workspace
from app.visual_summary.handoff.structured import _BLOCK_MENU, _SOURCE_HINT_BLOCK_TYPE
from app.visual_summary.planning.ui_intent import _AFFORDANCE_SPEC, KNOWN_SOURCE_HINTS
from app.visual_summary.workspace.context import (
    WorkspaceContextPacket,
    packet_from_dict,
)
from app.usage import estimate_tokens, log_usage

PROFILE_VERSION = 1

_KNOWN_TONES = ("instructional", "analytical", "executive", "casual")
_MAX_EXAMPLE_BLOCKS = 7


def context_fingerprint(
    *,
    name: str,
    description: str | None,
    tags: list[str] | None,
    document_rows: list[tuple[str, str]],
) -> str:
    """Stable hash of everything the profile is derived from."""
    ready = sorted(
        fn for fn, st in document_rows if (st or "").lower() == "ready"
    )[:50]
    blob = json.dumps(
        {
            "v": PROFILE_VERSION,
            "name": (name or "").strip(),
            "description": (description or "").strip(),
            "tags": sorted(str(t).strip() for t in (tags or []) if str(t).strip()),
            "documents": ready,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _affordance_menu() -> str:
    lines = []
    for affordance, (btype, _hint, _title) in _AFFORDANCE_SPEC.items():
        purpose = _BLOCK_MENU.get(btype, "")
        lines.append(f"  - {affordance}: {purpose or btype}")
    return "\n".join(lines)


def _format_profile_prompt(packet: WorkspaceContextPacket) -> str:
    i = packet.identity
    e = packet.evidence
    docs = ", ".join(e.documents_ready[:12]) or "(none yet)"
    return (
        "You profile a document workspace so an agent can frame answers and "
        "plan visual summaries for it. The workspace can be about ANYTHING — "
        "recipes, a study topic, job hunting, contracts, fitness, research.\n"
        "Derive the profile ONLY from the fields below; do not assume a domain "
        "that is not supported by them. Write phrases in the workspace's own "
        "language when the fields are not in English.\n\n"
        f"WORKSPACE NAME: {i.name or '(unnamed)'}\n"
        f"DESCRIPTION: {i.description or '(none)'}\n"
        f"TAGS: {', '.join(i.tags) or '(none)'}\n"
        f"DOCUMENTS: {docs}\n\n"
        "AFFORDANCE MENU (visual_affordances must come from these ids, "
        "best-fit first):\n"
        f"{_affordance_menu()}\n\n"
        "PLANNER EXAMPLE: also produce one example visual-summary layout that "
        "would be ideal for a typical question in this workspace. Use only "
        f"block types from: {', '.join(sorted(_BLOCK_MENU))}. Use only "
        f"source_hint values from: {', '.join(KNOWN_SOURCE_HINTS)}. "
        '2-5 blocks, each with type, title, source_hint, width ("full" or '
        '"half"), and purpose.\n\n'
        "Return JSON only:\n"
        "{\n"
        '  "domain_label": "short domain, e.g. cooking / personal recipe collection",\n'
        '  "outcome_phrase": "what the owner is trying to achieve (one sentence)",\n'
        '  "audience_phrase": "who reads the answers",\n'
        '  "success_criteria": "what a great answer accomplishes",\n'
        f'  "tone": "one of: {", ".join(_KNOWN_TONES)}",\n'
        '  "answer_sections": ["section name", ...],\n'
        '  "visual_affordances": ["affordance_id", ...],\n'
        '  "planner_example": {\n'
        '    "presentation_profile": "domain_layout e.g. mechanism_explainer",\n'
        '    "components": ["steps", ...],\n'
        '    "block_outline": [{"type": "steps", "title": "...", '
        '"source_hint": "ordered_actions", "width": "full", "purpose": "..."}],\n'
        '    "rationale": "one sentence"\n'
        "  }\n"
        "}"
    )


# Common off-menu names models use → canonical block type.
_TYPE_ALIASES: dict[str, str] = {
    "howto": "steps", "how_to": "steps", "procedure": "steps", "process": "steps",
    "checklist": "steps", "glossary": "key_terms", "definitions": "key_terms",
    "terms": "key_terms", "ingredients": "key_terms", "questions": "faq",
    "qna": "faq", "q_and_a": "faq", "overview": "summary", "intro": "summary",
    "bullets": "key_points", "points": "key_points", "highlights": "key_points",
    "tips": "key_points", "stats": "metrics", "kpis": "metrics",
    "matrix": "table", "compare": "comparison", "vs": "comparison",
    "warning": "callout", "note": "callout", "tip": "callout",
    "history": "timeline", "milestones": "timeline",
}

# Canonical source_hint per block type (inverse of hint→type), for repair
# when the model emits a hint that is not on the menu.
_DEFAULT_HINT_FOR_TYPE: dict[str, str] = {
    btype: hint for hint, btype in reversed(list(_SOURCE_HINT_BLOCK_TYPE.items()))
}


def sanitize_planner_example(raw: Any) -> dict[str, Any] | None:
    """Keep only grounded, well-formed outline entries; None when too thin."""
    if not isinstance(raw, dict):
        return None
    outline_raw = raw.get("block_outline")
    if not isinstance(outline_raw, list):
        return None
    valid_types = set(_BLOCK_MENU)
    valid_hints = set(KNOWN_SOURCE_HINTS)
    outline: list[dict[str, str]] = []
    for entry in outline_raw[:_MAX_EXAMPLE_BLOCKS]:
        if not isinstance(entry, dict):
            continue
        btype = str(entry.get("type") or "").strip().lower()
        btype = _TYPE_ALIASES.get(btype, btype)
        if btype not in valid_types:
            continue
        hint = str(entry.get("source_hint") or "").strip().lower()
        if hint not in valid_hints:
            hint = _DEFAULT_HINT_FOR_TYPE.get(btype, "")
        if hint not in valid_hints:
            continue
        width = str(entry.get("width") or "").strip()
        outline.append(
            {
                "type": btype,
                "title": str(entry.get("title") or "").strip()[:80] or btype,
                "source_hint": hint,
                "width": width if width in ("full", "half") else "full",
                "purpose": str(entry.get("purpose") or "").strip()[:160],
            }
        )
    if len(outline) < 2:
        return None
    profile = str(raw.get("presentation_profile") or "").strip()
    profile = "".join(
        c if c.isalnum() or c == "_" else "_" for c in profile.lower()
    ).strip("_") or "workspace_layout"
    components: list[str] = []
    for entry in outline:
        if entry["type"] not in components:
            components.append(entry["type"])
    return {
        "presentation_profile": profile[:60],
        "components": components,
        "block_outline": outline,
        "rationale": str(raw.get("rationale") or "").strip()[:240],
    }


def _apply_profile(
    packet: WorkspaceContextPacket, raw: dict[str, Any]
) -> WorkspaceContextPacket:
    """Overlay validated LLM fields onto the heuristic packet (in place)."""
    d = packet.derived

    for attr, limit in (
        ("domain_label", 120),
        ("outcome_phrase", 200),
        ("audience_phrase", 120),
        ("success_criteria", 200),
    ):
        value = raw.get(attr)
        if isinstance(value, str) and value.strip():
            setattr(d, attr, value.strip()[:limit])

    tone = str(raw.get("tone") or "").strip().lower()
    if tone in _KNOWN_TONES:
        d.tone = tone

    affordances = [
        str(a).strip()
        for a in (raw.get("visual_affordances") or [])
        if str(a).strip() in _AFFORDANCE_SPEC
    ]
    if affordances:
        # Keep heuristic extras the LLM missed, after the LLM's ranking.
        d.visual_affordances = affordances + [
            a for a in d.visual_affordances if a not in affordances
        ]

    sections = [
        str(s).strip()[:60]
        for s in (raw.get("answer_sections") or [])
        if str(s).strip()
    ]
    if sections:
        d.answer_sections = sections[:8]

    example = sanitize_planner_example(raw.get("planner_example"))
    if example:
        d.planner_example = example

    packet.meta.confidence = "high"
    return packet


def derive_workspace_profile_llm(
    packet: WorkspaceContextPacket,
    *,
    db: Session | None = None,
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> WorkspaceContextPacket | None:
    """One profiling call; returns the enriched packet or None on failure."""
    prompt = _format_profile_prompt(packet)
    try:
        resp = _client().chat.completions.create(
            model=settings.visual_summary_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You profile document workspaces for agent framing and "
                        "visual layout planning. JSON only. Never invent facts "
                        "the workspace fields do not support."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
        raw_text = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw_text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None

    if db is not None and workspace_id is not None:
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = estimate_tokens(prompt)
            completion_tokens = estimate_tokens(raw_text)
        log_usage(
            db,
            kind="workspace_profile",
            model=settings.visual_summary_model,
            user_id=user_id,
            workspace_id=workspace_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            meta={"workspace": packet.identity.name[:120]},
        )

    return _apply_profile(packet, parsed)


def resolve_profiled_packet(
    db: Session,
    ws: Workspace,
    *,
    document_rows: list[tuple[str, str]],
    heuristic: WorkspaceContextPacket,
    user_id: uuid.UUID | None = None,
) -> WorkspaceContextPacket:
    """Cached profile when fresh; profile+cache on change; heuristic otherwise."""
    fingerprint = context_fingerprint(
        name=ws.name or "",
        description=ws.description,
        tags=ws.tags if isinstance(ws.tags, list) else None,
        document_rows=document_rows,
    )

    cache = ws.context_cache if isinstance(ws.context_cache, dict) else None
    if (
        cache
        and cache.get("fingerprint") == fingerprint
        and isinstance(cache.get("packet"), dict)
    ):
        cached = packet_from_dict(cache["packet"])
        # Evidence (doc lists/counts) may drift without changing the
        # fingerprint's ready-set semantics; always serve it fresh.
        cached.evidence = heuristic.evidence
        return cached

    if not (settings.workspace_llm_profiler and settings.openai_api_key):
        return heuristic

    profiled = derive_workspace_profile_llm(
        heuristic,
        db=db,
        workspace_id=ws.id,
        user_id=user_id,
    )
    if profiled is None:
        return heuristic  # not cached — retried on the next run

    try:
        ws.context_cache = {
            "fingerprint": fingerprint,
            "version": PROFILE_VERSION,
            "packet": profiled.to_dict(),
        }
        db.add(ws)
        db.commit()
    except Exception:
        db.rollback()
    return profiled
