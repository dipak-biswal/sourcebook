"""Agents package: main + visual summary + workspace context.

Canonical layout:

- ``app.agents.main`` — main tool-using agent (runner, tools, profiles, trace)
- ``app.agents.visual_summary`` — Visual Summary agent (handoff → plan → render)
- ``app.agents.context`` — pre-main Workspace Context agent (readiness + HITL)

Convenience re-exports for the main runner entry points:
"""

from app.agents.main.runner import approve_agent_run, run_agent

__all__ = ["approve_agent_run", "run_agent"]
