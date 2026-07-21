"""Agents package: main workspace agent + visual summary agent.

Canonical layout:

- ``app.agents.main`` — main tool-using agent (runner, tools, profiles, trace)
- ``app.agents.visual_summary`` — Visual Summary agent (handoff → plan → render)

Convenience re-exports for the main runner entry points:
"""

from app.agents.main.runner import approve_agent_run, run_agent

__all__ = ["approve_agent_run", "run_agent"]
