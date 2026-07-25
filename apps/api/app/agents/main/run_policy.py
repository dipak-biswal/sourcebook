"""Per-run tool policy for the main workspace agent.

Derives web/date requirements from workspace packet + HITL snapshot so the
agent does not always burn a get_current_date + web_search turn.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.context.merge import CollectedContextSnapshot
from app.agents.visual_summary.workspace.context import WorkspaceContextPacket

# Goals that usually need "today" for correct web search years or recency.
_TIME_SENSITIVE = re.compile(
    r"\b("
    r"today|tonight|this\s+week|this\s+month|this\s+year|current|currently|"
    r"latest|recent|recently|up[\s-]?to[\s-]?date|news|market|salary|"
    r"hiring|trends?|202[4-9]|203\d|as\s+of|right\s+now|nowadays"
    r")\b",
    re.I,
)


def goal_is_time_sensitive(goal: str) -> bool:
    g = (goal or "").strip()
    if not g:
        return False
    return bool(_TIME_SENSITIVE.search(g))


def _normalize_evidence_plan(raw: str) -> str:
    """Map HITL document_plan labels to: docs | web | both | unknown."""
    t = (raw or "").strip().lower()
    if not t:
        return "unknown"
    # Checkbox ids and pretty labels from merge.
    if t in ("upload", "documents", "workspace documents", "workspace"):
        return "docs"
    if "both" in t:
        return "both"
    if t in ("web",) or t.startswith("use the web") or t == "web only":
        return "web"
    if "document" in t and "web" not in t:
        return "docs"
    if "web" in t and "document" not in t and "both" not in t:
        return "web"
    return "unknown"


def apply_snapshot_to_tool_policy(
    packet: WorkspaceContextPacket,
    snapshot: CollectedContextSnapshot | None,
) -> dict[str, Any]:
    """
    Mutate packet.derived.tool_policy from HITL evidence preferences.

    Returns a small summary for tracing, including granular tool gates:
    allow_web_search vs allow_fetch_url (docs-only + user URLs → fetch only).
    """
    policy = packet.derived.tool_policy
    before = bool(policy.external_context_ok)
    plan = _normalize_evidence_plan(snapshot.document_plan if snapshot else "")
    urls = list(snapshot.urls) if snapshot else []

    # Defaults follow workspace-derived external_context_ok until HITL overrides.
    allow_web_search = before
    allow_fetch_url = before

    if plan == "docs":
        if urls:
            # Documents first; user-supplied URLs may be fetched, but no open web search.
            policy.external_context_ok = True
            allow_web_search = False
            allow_fetch_url = True
            policy.max_web_search = 0
            if policy.max_fetch_url <= 0:
                policy.max_fetch_url = 2
        else:
            policy.external_context_ok = False
            allow_web_search = False
            allow_fetch_url = False
            policy.max_web_search = 0
            policy.max_fetch_url = 0
    elif plan in ("web", "both"):
        policy.external_context_ok = True
        allow_web_search = True
        allow_fetch_url = True
        if policy.max_web_search <= 0:
            policy.max_web_search = 1
        if policy.max_fetch_url <= 0:
            policy.max_fetch_url = 2
    else:
        # unknown: leave workspace-derived defaults; still ensure fetch if URLs given.
        if urls and policy.max_fetch_url <= 0:
            policy.max_fetch_url = 2
            allow_fetch_url = True
            policy.external_context_ok = True

    after = bool(policy.external_context_ok)
    return {
        "evidence_plan": plan,
        "external_context_ok_before": before,
        "external_context_ok_after": after,
        "allow_web_search": allow_web_search,
        "allow_fetch_url": allow_fetch_url,
        "url_count": len(urls),
    }


def run_requires_date_tool(
    *,
    allow_web: bool,
    goal: str,
    snapshot: CollectedContextSnapshot | None = None,
    curated_goal: str = "",
    allow_fetch_url: bool | None = None,
) -> bool:
    """
    Whether the main agent must resolve current date this run.

    Required when web search is allowed (year-stamped queries), when fetch_url
    is allowed (page dates / recency), when the user provided URLs, or when the
    goal is clearly about current/latest information.
    """
    if allow_web:
        return True
    if allow_fetch_url:
        return True
    if snapshot and snapshot.urls:
        return True
    blob = f"{goal or ''}\n{curated_goal or ''}"
    if snapshot and snapshot.topic_focus:
        blob = f"{blob}\n{snapshot.topic_focus}"
    return goal_is_time_sensitive(blob)


def format_run_tool_policy_block(
    *,
    allow_web: bool,
    require_date: bool,
    evidence_plan: str = "unknown",
    ready_doc_count: int = 0,
    allow_fetch_url: bool | None = None,
) -> str:
    """Injected system block — overrides generic tool-order defaults for this run."""
    fetch_ok = allow_web if allow_fetch_url is None else bool(allow_fetch_url)
    lines = [
        "RUN TOOL POLICY (authoritative for this run — overrides generic tool-order defaults):",
    ]
    if require_date:
        lines.append(
            "- get_current_date: REQUIRED before web_search/fetch_url, and before "
            "any time-sensitive claims. Prefer calling it first when you will use the web."
        )
    else:
        lines.append(
            "- get_current_date: OPTIONAL this run (no web search and goal is not "
            "time-sensitive). Do not call it unless you need a calendar date for the answer."
        )

    if allow_web:
        lines.append(
            "- web_search: ALLOWED. Prefer workspace documents first when "
            f"ready docs exist (ready={ready_doc_count}); use web for gaps, definitions, "
            "or when the user asked for public/web evidence."
        )
        if fetch_ok:
            lines.append(
                "- fetch_url: ALLOWED for pages from web_search or user-provided URLs."
            )
        if evidence_plan == "web":
            lines.append(
                "- Evidence plan: WEB-FIRST. Still label every web-sourced claim clearly."
            )
        elif evidence_plan == "both":
            lines.append(
                "- Evidence plan: BOTH docs and web. Synthesize carefully; mark sources."
            )
    elif fetch_ok:
        lines.append(
            "- web_search: OFF for this run. "
            "Use list_documents / search_documents / read_document for workspace evidence."
        )
        lines.append(
            "- fetch_url: ALLOWED only for user-provided URLs (no open web search). "
            "Label fetched pages as user-provided / external."
        )
        if evidence_plan == "docs":
            lines.append(
                "- Evidence plan: WORKSPACE DOCUMENTS + optional user URLs (user confirmed)."
            )
    else:
        lines.append(
            "- web_search / fetch_url: OFF for this run (user or workspace policy). "
            "Use list_documents / search_documents / read_document only. "
            "If evidence is insufficient, say what is missing — do not invent web facts."
        )
        if evidence_plan == "docs":
            lines.append(
                "- Evidence plan: WORKSPACE DOCUMENTS ONLY (user confirmed)."
            )

    lines.extend(
        [
            "- Grounding: every non-trivial claim should be supported by a tool result "
            "or an explicit user-provided fact from COLLECTED RUN CONTEXT / curated brief.",
            "- Source labels: when mixing sources, mark workspace vs web vs user-provided.",
            "- Finish with a written answer; never stop on tool calls alone.",
        ]
    )
    return "\n".join(lines)


def evidence_constraint_lines(
    *,
    evidence_plan: str,
    allow_web: bool,
    allow_fetch_url: bool = False,
    urls: list[str] | None = None,
) -> list[str]:
    """Short constraints for curator addenda (LLM + heuristic)."""
    lines: list[str] = []
    if evidence_plan == "docs" and not allow_web and not allow_fetch_url:
        lines.append(
            "- Evidence constraint: workspace documents only — do not rely on public web research."
        )
    elif evidence_plan == "docs" and allow_fetch_url and not allow_web:
        lines.append(
            "- Evidence constraint: workspace documents first; only fetch user-provided URLs "
            "(no open web search)."
        )
        if urls:
            lines.append(f"- User URLs to consider: {', '.join(urls[:8])}")
    elif evidence_plan == "web":
        lines.append(
            "- Evidence constraint: user prefers web research; still prefer workspace docs "
            "when ready, and label every web-sourced claim."
        )
    elif evidence_plan == "both":
        lines.append(
            "- Evidence constraint: synthesize workspace documents and web; mark sources clearly."
        )
    if not allow_web and not allow_fetch_url:
        lines.append(
            "- If documents are insufficient, state what is missing rather than inventing facts."
        )
    return lines


def apply_tool_policy_to_base_prompt(
    base_prompt: str,
    *,
    require_date: bool,
    allow_web: bool,
    allow_fetch_url: bool | None = None,
) -> str:
    """
    Soften absolute MUST-get_current_date language when date is optional,
    and strip web tools from the advertised tool list when web is off.
    """
    fetch_ok = allow_web if allow_fetch_url is None else bool(allow_fetch_url)
    text = base_prompt
    if not require_date:
        # Legacy absolute MUST language (older prompt revisions).
        text = re.sub(
            r"- Your FIRST tool call in every run MUST be get_current_date[^\n]*\n",
            "- get_current_date is optional this run (see RUN TOOL POLICY). Start with "
            "workspace document tools when answering from uploads.\n",
            text,
        )
        # Current policy-aware wording: reinforce optional date.
        text = re.sub(
            r"- When RUN TOOL POLICY requires a date[^\n]*\n",
            "- get_current_date is optional this run (see RUN TOOL POLICY). Start with "
            "workspace document tools when answering from uploads.\n",
            text,
        )
        text = re.sub(
            r"- Do not call web_search or fetch_url until get_current_date has returned "
            r"in this run[^\n]*\n",
            "",
            text,
        )
    if not allow_web and not fetch_ok:
        text = text.replace(", web_search, fetch_url", "")
        text = text.replace("web_search, fetch_url, ", "")
        text = re.sub(
            r"- RESEARCH FALLBACK:.*?(?=\n- |\nANSWER|\nWhen finished|\Z)",
            "- RESEARCH FALLBACK: web tools are OFF — if documents are missing, "
            "state that clearly and suggest uploads or enabling web evidence.\n",
            text,
            flags=re.S,
        )
    elif not allow_web and fetch_ok:
        text = text.replace(", web_search, fetch_url", ", fetch_url")
        text = text.replace("web_search, fetch_url, ", "fetch_url, ")
        text = re.sub(
            r"- RESEARCH FALLBACK:.*?(?=\n- |\nANSWER|\nWhen finished|\Z)",
            "- RESEARCH FALLBACK: web_search is OFF — use workspace documents and "
            "fetch_url only for user-provided URLs; do not invent public web facts.\n",
            text,
            flags=re.S,
        )
    return text
