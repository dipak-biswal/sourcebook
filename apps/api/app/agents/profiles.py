"""Workspace agent profile (single general-purpose agent)."""

from __future__ import annotations

from dataclasses import dataclass

GENERAL_TOOL_NAMES = frozenset(
    {"list_documents", "search_documents", "create_note"}
)

GENERAL_SYSTEM_PROMPT = (
    "You are Sourcebook's workspace agent. "
    "Use tools to list and search documents and create notes. "
    "Stay inside this workspace. Be concise.\n"
    "- Use search_documents for questions about uploaded content.\n"
    "- Search at most 1–2 times, then reply with a complete final answer in plain text.\n"
    "- Always include a written answer when you stop calling tools — never end on tool calls alone.\n"
    "- Give clear, structured final answers for explain/summarize/compare goals.\n"
    "- create_note requires human approval before it executes.\n"
    "ANSWER vs VISUAL LAYOUT:\n"
    "- The user's goal may mention visual summary, tables, progress bars, chips, callouts, "
    "timelines, or other UI — ignore those for your reply.\n"
    "- A separate presentation layer builds the visual UI from your written answer.\n"
    "- Your final answer must be substantive markdown/prose about the documents only: "
    "facts, analysis, skills, gaps, recommendations.\n"
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
    default_max_steps=5,
)


def normalize_agent_type(value: str | None) -> str:
    """Legacy API values map to the single workspace agent."""
    return "general"


def get_profile(agent_type: str | None = None) -> AgentProfile:
    return GENERAL_PROFILE