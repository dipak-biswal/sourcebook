"""Workspace agent profile (single general-purpose agent)."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.main.tools.date import DATE_TOOL_NAMES
from app.prompts.agent import (
    GENERAL_SYSTEM_PROMPT,
    VISUAL_SUMMARY_SYSTEM_PROMPT,
)

# Re-export for existing imports.
__all__ = [
    "GENERAL_SYSTEM_PROMPT",
    "VISUAL_SUMMARY_SYSTEM_PROMPT",
    "GENERAL_TOOL_NAMES",
    "VISUAL_SUMMARY_TOOL_NAMES",
    "AgentProfile",
    "GENERAL_PROFILE",
    "VISUAL_SUMMARY_PROFILE",
    "normalize_agent_type",
    "agent_system_prompt",
    "get_profile",
]

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
