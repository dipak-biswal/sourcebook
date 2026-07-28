"""Prompt-curator agent: build a curated main-agent brief from workspace + HITL."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.agents.context.merge import CollectedContextSnapshot
from app.agents.main.run_policy import evidence_constraint_lines
from app.agents.visual_summary.llm_json import chat_json
from app.agents.visual_summary.workspace.context import WorkspaceContextPacket
from app.config import settings
from app.prompts.context import CURATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

CURATED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "system_addendum": {"type": "string"},
        "curated_goal": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["system_addendum", "curated_goal", "rationale"],
    "additionalProperties": False,
}

_SYSTEM = CURATOR_SYSTEM_PROMPT


def _append_policy_constraints(
    addendum: str,
    *,
    snapshot: CollectedContextSnapshot | None,
    policy_summary: dict[str, Any] | None,
) -> str:
    """Ensure HITL evidence constraints survive LLM rewrite of the brief."""
    if not policy_summary:
        return addendum
    plan = str(policy_summary.get("evidence_plan") or "unknown")
    allow_web = bool(policy_summary.get("allow_web_search", policy_summary.get("allow_web")))
    allow_fetch = bool(policy_summary.get("allow_fetch_url", allow_web))
    urls = list(snapshot.urls) if snapshot else []
    constraints = evidence_constraint_lines(
        evidence_plan=plan,
        allow_web=allow_web,
        allow_fetch_url=allow_fetch,
        urls=urls,
    )
    if not constraints:
        return addendum
    text = (addendum or "").rstrip()
    # Skip lines already present (case-insensitive substring).
    lower = text.lower()
    extra = [ln for ln in constraints if ln.lstrip("- ").lower() not in lower]
    if not extra:
        return text
    return f"{text}\n" + "\n".join(extra) if text else "\n".join(extra)


def _model_name() -> str:
    return (
        (settings.context_curator_model or "").strip()
        or (settings.context_agent_model or "").strip()
        or settings.chat_model
    )


def _heuristic_curation(
    packet: WorkspaceContextPacket,
    goal: str,
    snapshot: CollectedContextSnapshot | None,
    policy_summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Deterministic brief when LLM is off or fails."""
    lines = [
        "CURATED RUN BRIEF (from workspace context + user plan):",
    ]
    if packet.identity.name:
        lines.append(f"- Workspace: {packet.identity.name}")
    if packet.identity.description:
        lines.append(f"- Workspace purpose: {packet.identity.description[:400]}")
    if packet.derived.audience_phrase:
        lines.append(f"- Audience: {packet.derived.audience_phrase}")
    if packet.derived.outcome_phrase:
        lines.append(f"- Desired outcome: {packet.derived.outcome_phrase}")
    if packet.derived.tone:
        lines.append(f"- Tone: {packet.derived.tone}")
    if snapshot and not snapshot.is_empty():
        if snapshot.topic_focus:
            lines.append(f"- Confirmed focus: {snapshot.topic_focus}")
        if snapshot.audience:
            lines.append(f"- Confirmed audience: {snapshot.audience}")
        if snapshot.level:
            lines.append(f"- Level: {snapshot.level}")
        if snapshot.document_plan:
            lines.append(f"- Evidence plan: {snapshot.document_plan}")
        if snapshot.urls:
            lines.append(f"- Prefer URLs: {', '.join(snapshot.urls)}")
        if snapshot.must_cover:
            lines.append(f"- Must cover: {snapshot.must_cover}")
        for k, v in snapshot.extra.items():
            lines.append(f"- {k.replace('_', ' ')}: {v}")
    if policy_summary:
        plan = str(policy_summary.get("evidence_plan") or "unknown")
        allow_web = bool(
            policy_summary.get("allow_web_search", policy_summary.get("allow_web"))
        )
        allow_fetch = bool(policy_summary.get("allow_fetch_url", allow_web))
        lines.extend(
            evidence_constraint_lines(
                evidence_plan=plan,
                allow_web=allow_web,
                allow_fetch_url=allow_fetch,
                urls=list(snapshot.urls) if snapshot else None,
            )
        )
    lines.append(
        "- Prefer workspace documents when ready; use web only when policy allows "
        "and docs are insufficient."
    )
    lines.append("- Be concise, ground claims in tool results, and cite sources.")

    curated_goal = (goal or "").strip()
    if snapshot and snapshot.topic_focus:
        curated_goal = (
            f"{curated_goal}\n\nFocus for this run: {snapshot.topic_focus}"
        ).strip()
    if snapshot and snapshot.must_cover:
        curated_goal = (
            f"{curated_goal}\nMust cover / constraints: {snapshot.must_cover}"
        ).strip()

    return {
        "system_addendum": "\n".join(lines),
        "curated_goal": curated_goal or goal,
        "rationale": "Heuristic brief from workspace + HITL answers.",
        "source": "heuristic",
    }


def curate_main_agent_prompt(
    packet: WorkspaceContextPacket,
    goal: str,
    snapshot: CollectedContextSnapshot | None,
    policy_summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Return {system_addendum, curated_goal, rationale, source}.

    Uses a cheap model when enabled; always has a heuristic fallback.
    Evidence constraints from ``policy_summary`` are always appended so an
    LLM rewrite cannot drop docs-only / no-web rules.
    """
    base = _heuristic_curation(packet, goal, snapshot, policy_summary=policy_summary)
    if not getattr(settings, "context_curator_enabled", True):
        return base
    if not settings.openai_api_key:
        return base

    snap_blob = ""
    if snapshot and not snapshot.is_empty():
        snap_blob = json.dumps(snapshot.to_dict(), ensure_ascii=False)

    web_allowed = bool(packet.derived.tool_policy.external_context_ok)
    if policy_summary is not None:
        web_allowed = bool(
            policy_summary.get("allow_web_search", policy_summary.get("allow_web", web_allowed))
        )
    fetch_allowed = web_allowed
    if policy_summary is not None and "allow_fetch_url" in policy_summary:
        fetch_allowed = bool(policy_summary.get("allow_fetch_url"))

    user = (
        f"USER PLAN / GOAL:\n{(goal or '').strip()}\n\n"
        f"WORKSPACE NAME: {packet.identity.name}\n"
        f"WORKSPACE DESCRIPTION:\n{(packet.identity.description or '')[:800] or '(none)'}\n"
        f"TAGS: {', '.join(packet.identity.tags or []) or '(none)'}\n"
        f"OUTCOME: {packet.derived.outcome_phrase}\n"
        f"AUDIENCE: {packet.derived.audience_phrase}\n"
        f"TONE: {packet.derived.tone}\n"
        f"READY DOCS: {', '.join((packet.evidence.documents_ready or [])[:12]) or '(none)'}\n"
        f"WEB SEARCH ALLOWED: {web_allowed}\n"
        f"FETCH URL ALLOWED: {fetch_allowed}\n"
        f"EVIDENCE PLAN: {(policy_summary or {}).get('evidence_plan', 'unknown')}\n\n"
        f"HITL ANSWERS JSON:\n{snap_blob or '{}'}\n\n"
        "Produce system_addendum and curated_goal."
    )

    try:
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=45.0,
            max_retries=2,
        )
        resp = chat_json(
            client,
            model=_model_name(),
            system=_SYSTEM,
            prompt=user,
            schema_name="curated_brief",
            schema=CURATED_SCHEMA,
            temperature=0.2,
            max_tokens=700,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content) if content else {}
        if not isinstance(data, dict):
            return base
        addendum = str(data.get("system_addendum") or "").strip()
        curated = str(data.get("curated_goal") or "").strip()
        rationale = str(data.get("rationale") or "").strip()
        if not addendum or not curated:
            return base
        addendum = _append_policy_constraints(
            addendum, snapshot=snapshot, policy_summary=policy_summary
        )
        return {
            "system_addendum": addendum[:4000],
            "curated_goal": curated[:2000],
            "rationale": rationale[:400] or base["rationale"],
            "source": "llm",
            "model": _model_name(),
        }
    except Exception:
        logger.exception("context curator LLM failed; using heuristic brief")
        return base
