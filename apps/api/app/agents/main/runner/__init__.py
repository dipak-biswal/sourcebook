"""Agent tool loop with human-in-the-loop and resume-after-approve.

Facade for the runner package — import from `app.agents.main.runner` as before:

- lifecycle: run_agent, approve_agent_run
- serialization: run_to_public_dict, step_to_dict
- constants: WRITE_TOOLS, PRESENTATION_TOOL, EventCallback

Submodule imports (e.g. ``from app.agents.main.runner.constants import …``) must not
pull lifecycle/loop eagerly — keep this package init lazy to avoid circular
imports with ``visual_summary.pipeline``.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EventCallback",
    "PRESENTATION_TOOL",
    "WRITE_TOOLS",
    "approve_agent_run",
    "run_agent",
    "run_to_public_dict",
    "step_to_dict",
    "_hash_args",
    "_tool_context_for_synthesis",
    "_weak_final_answer",
    "_workspace_name_for_run",
]


def __getattr__(name: str) -> Any:
    if name in ("PRESENTATION_TOOL", "WRITE_TOOLS"):
        from app.agents.main.runner import constants as _c

        return getattr(_c, name)
    if name in ("EventCallback", "run_to_public_dict", "step_to_dict", "_workspace_name_for_run"):
        from app.agents.main.runner import events as _e

        return getattr(_e, name)
    if name in ("run_agent", "approve_agent_run"):
        from app.agents.main.runner import lifecycle as _l

        return getattr(_l, name)
    if name == "_hash_args":
        from app.agents.main.runner.messages import _hash_args

        return _hash_args
    if name in ("_tool_context_for_synthesis", "_weak_final_answer"):
        from app.agents.main.runner import synthesis as _s

        return getattr(_s, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
