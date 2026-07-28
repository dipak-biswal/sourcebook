"""Central library of LLM system / instruction prompts.

Import from here (or submodules) instead of inlining long prompt strings
across agents, learn, curriculum, and chat.
"""

from app.prompts.agent import (
    GENERAL_SYSTEM_PROMPT,
    VISUAL_SUMMARY_SYSTEM_PROMPT,
)
from app.prompts.chat import (
    CHAT_ANSWER_PROMPT,
    CHAT_SUGGEST_QUESTIONS_PROMPT,
)
from app.prompts.context import CURATOR_SYSTEM_PROMPT
from app.prompts.learn import (
    CURRICULUM_CHAPTERS_SYSTEM,
    LEARN_LESSON_SYSTEM,
    LEARN_SUGGEST_SETUP_SYSTEM,
)
from app.prompts.visual import (
    VISUAL_EXTRACT_SYSTEM,
    VISUAL_PLAN_SYSTEM,
)
from app.prompts.workspace_curator import (
    WORKSPACE_CURATOR_CURRICULUM_SYSTEM,
    WORKSPACE_CURATOR_DESCRIPTION_SYSTEM,
)

__all__ = [
    "GENERAL_SYSTEM_PROMPT",
    "VISUAL_SUMMARY_SYSTEM_PROMPT",
    "CHAT_ANSWER_PROMPT",
    "CHAT_SUGGEST_QUESTIONS_PROMPT",
    "CURATOR_SYSTEM_PROMPT",
    "CURRICULUM_CHAPTERS_SYSTEM",
    "LEARN_LESSON_SYSTEM",
    "LEARN_SUGGEST_SETUP_SYSTEM",
    "VISUAL_EXTRACT_SYSTEM",
    "VISUAL_PLAN_SYSTEM",
    "WORKSPACE_CURATOR_CURRICULUM_SYSTEM",
    "WORKSPACE_CURATOR_DESCRIPTION_SYSTEM",
]
