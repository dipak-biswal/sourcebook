"""Workspace agent profile (single general-purpose agent)."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.date_tools import DATE_TOOL_NAMES

GENERAL_TOOL_NAMES = frozenset(
    {
        "list_documents",
        "search_documents",
        "read_document",
        "web_search",
        "fetch_url",
        "create_note",
        *DATE_TOOL_NAMES,
    }
)

# Generic template — workspace-specific framing is injected as WorkspaceContextPacket.
GENERAL_SYSTEM_PROMPT = (
    "You are Sourcebook's workspace agent. "
    "You have these tools: get_current_date, list_documents, search_documents, "
    "read_document, web_search, fetch_url, create_note.\n"
    "Stay focused on the user's goal within the WORKSPACE CONTEXT provided with "
    "each run. Be concise and match the derived tone.\n"
    "TOOL ORDER (required):\n"
    "- Your FIRST tool call in every run MUST be get_current_date — before "
    "list_documents, search_documents, read_document, web_search, fetch_url, "
    "or create_note.\n"
    "- Use the returned year/month in web_search queries; never use outdated years "
    "(e.g. 2023) for current-market searches.\n"
    "- Do not call web_search or fetch_url until get_current_date has returned in "
    "this run.\n"
    "- Use search_documents for facts in uploaded workspace files.\n"
    "- Use read_document when search snippets are not enough and you need a "
    "document's full text; paginate with start_chunk when has_more is true.\n"
    "- Use web_search only when WORKSPACE CONTEXT tool policy allows external "
    "context and workspace documents are insufficient (definitions, benchmarks, "
    "public background). If web_search is OFF or not available, do not attempt it.\n"
    "- If fetch_url returns an error (HTTP 403/404/etc.), do NOT stop or wait for "
    "the user — treat it as a failed tool, try another URL from web_search, or "
    "answer from the snippets you already have and note the source was blocked.\n"
    "- Use fetch_url (when available) to read a page found via web_search or a URL "
    "the user included in their goal.\n"
    "- RESEARCH FALLBACK: if WORKSPACE CONTEXT shows no ready documents, do NOT "
    "stop at 'no documents found' — research the goal with web_search and "
    "fetch_url (when available), fetch any URL in the user's goal first, and "
    "clearly label the answer as web-sourced.\n"
    "- Prefer workspace evidence first. Respect max search limits in WORKSPACE CONTEXT.\n"
    "- Cite web findings briefly when used; distinguish workspace facts from web context.\n"
    "- Always include a written answer when you stop calling tools — never end on tool calls alone.\n"
    "- Shape the final answer using suggested answer sections from WORKSPACE CONTEXT "
    "when they fit the evidence; add or drop sections only when supported by evidence.\n"
    "- Aim for the workspace success criteria in your conclusion or next steps.\n"
    "- create_note requires human approval before it executes.\n"
    "ANSWER vs VISUAL LAYOUT:\n"
    "- The user's goal may mention visual summary, tables, progress bars, chips, callouts, "
    "timelines, or other UI — ignore those for your reply.\n"
    "- A separate presentation layer builds the visual UI from your written answer.\n"
    "- Your final answer must be substantive markdown/prose grounded in workspace "
    "documents (and allowed web context): facts, analysis, recommendations.\n"
    "- Never list UI component names, never describe what widgets will be shown, "
    "never output layout instructions.\n"
    "When finished, answer clearly without more tool calls."
)


@dataclass(frozen=True)
class AgentProfile:
    agent_type: str
    system_prompt: str
    tool_names: frozenset[str]
    default_max_steps: int


GENERAL_PROFILE = AgentProfile(
    agent_type="general",
    system_prompt=GENERAL_SYSTEM_PROMPT,
    tool_names=GENERAL_TOOL_NAMES,
    default_max_steps=8,
)

VISUAL_SUMMARY_TOOL_NAMES = frozenset({"plan_layout", "render_ui", *DATE_TOOL_NAMES})

VISUAL_SUMMARY_SYSTEM_PROMPT = (
    "You are the Visual Summary Agent. The workspace agent already finished — you only "
    "plan and render UI from structured content extracted from its answer.\n"
    "Your job is to orchestrate tools — not re-analyze documents or rewrite the answer.\n"
    "- Call plan_layout once first (structured input is injected automatically from the handoff).\n"
    "- plan_layout auto-validates and may replan once internally — do NOT call plan_layout "
    "again unless status is validation_failed and validation_errors are non-empty.\n"
    "- If validation_failed, you may call plan_layout ONE more time with notes summarizing "
    "the validation_errors — never more than two plan_layout calls total.\n"
    "- When validation_status is passed (or layout_plan looks complete), call render_ui with "
    "the layout plan as a JSON string.\n"
    "- Do not invent facts; render only what the main agent already established.\n"
    "- Call get_current_date when you need today's date, month, or year for labels or timelines.\n"
    "- After render_ui succeeds, reply briefly that the visual summary is ready — no more tools."
)

VISUAL_SUMMARY_PROFILE = AgentProfile(
    agent_type="visual_summary",
    system_prompt=VISUAL_SUMMARY_SYSTEM_PROMPT,
    tool_names=VISUAL_SUMMARY_TOOL_NAMES,
    default_max_steps=4,
)

_PROFILES: dict[str, AgentProfile] = {
    "general": GENERAL_PROFILE,
    "visual_summary": VISUAL_SUMMARY_PROFILE,
}


def normalize_agent_type(value: str | None) -> str:
    """Legacy API values map to the single workspace agent."""
    return "general"


def agent_system_prompt(base: str | None = None) -> str:
    """Return the agent system prompt (date comes from get_current_date tool)."""
    return base or GENERAL_SYSTEM_PROMPT


def get_profile(agent_type: str | None = None) -> AgentProfile:
    key = (agent_type or "general").strip() or "general"
    return _PROFILES.get(key, GENERAL_PROFILE)
