"""Agent tool loop with human-in-the-loop and resume-after-approve.

Facade for the runner package — import from `app.agents.runner` as before:

- lifecycle: run_agent, approve_agent_run
- serialization: run_to_public_dict, step_to_dict
- constants: WRITE_TOOLS, PRESENTATION_TOOL, EventCallback
"""

from app.agents.runner.constants import PRESENTATION_TOOL, WRITE_TOOLS
from app.agents.runner.events import (
    EventCallback,
    _workspace_name_for_run,
    run_to_public_dict,
    step_to_dict,
)
from app.agents.runner.lifecycle import approve_agent_run, run_agent
from app.agents.runner.messages import _hash_args
from app.agents.runner.synthesis import (
    _tool_context_for_synthesis,
    _weak_final_answer,
)

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
