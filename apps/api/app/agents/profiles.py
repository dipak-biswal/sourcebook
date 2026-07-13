"""Agent profiles: tool sets and system prompts per agent type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentType = Literal["general", "study_guide"]

GENERAL_TOOL_NAMES = frozenset(
    {"list_documents", "search_documents", "create_note"}
)
STUDY_GUIDE_TOOL_NAMES = frozenset(
    {"list_documents", "search_documents", "study_guide", "create_note"}
)

GENERAL_SYSTEM_PROMPT = (
    "You are Sourcebook's workspace agent. "
    "Use tools to list and search documents and create notes. "
    "Stay inside this workspace. Be concise.\n"
    "- Use search_documents for questions about uploaded content.\n"
    "- create_note requires human approval before it executes.\n"
    "When finished, answer clearly without more tool calls."
)

STUDY_GUIDE_SYSTEM_PROMPT = (
    "You are Sourcebook's Study Guide agent. "
    "Your job is to turn workspace documents into clear, cited learning views.\n"
    "- For explain / summarize simply / teach me / overview / key points / FAQ / "
    "glossary requests, call study_guide with a clear topic (and optional focus).\n"
    "- If the user names a file, call list_documents if needed, then pass "
    "document_id or document_filename into study_guide.\n"
    "- search_documents can help pick a topic or file before study_guide.\n"
    "- After study_guide succeeds, give a short text answer and mention that a "
    "structured learning view is shown in the UI.\n"
    "- create_note requires human approval. Use it only when the user asks to save "
    "content as a note.\n"
    "Prefer one study_guide call per user goal. Do not loop on study_guide."
)


@dataclass(frozen=True)
class AgentProfile:
    agent_type: AgentType
    system_prompt: str
    tool_names: frozenset[str]
    default_max_steps: int


_PROFILES: dict[AgentType, AgentProfile] = {
    "general": AgentProfile(
        agent_type="general",
        system_prompt=GENERAL_SYSTEM_PROMPT,
        tool_names=GENERAL_TOOL_NAMES,
        default_max_steps=5,
    ),
    "study_guide": AgentProfile(
        agent_type="study_guide",
        system_prompt=STUDY_GUIDE_SYSTEM_PROMPT,
        tool_names=STUDY_GUIDE_TOOL_NAMES,
        default_max_steps=4,
    ),
}


def normalize_agent_type(value: str | None) -> AgentType:
    if value == "study_guide":
        return "study_guide"
    return "general"


def get_profile(agent_type: str | None) -> AgentProfile:
    return _PROFILES[normalize_agent_type(agent_type)]