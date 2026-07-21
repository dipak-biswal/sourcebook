"""Input bundle for the presentation engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.visual_summary.handoff.evidence import AgentEvidenceBundle


@dataclass
class PresentationContext:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    goal: str
    final_answer: str
    workspace_name: str = ""
    workspace_description: str = ""
    workspace_tags: list[str] = field(default_factory=list)
    document_filenames: list[str] = field(default_factory=list)
    agent_evidence: AgentEvidenceBundle = field(default_factory=AgentEvidenceBundle)
    structured_content: dict | None = None
    # How structured_content was resolved: "heuristic" | "llm" | "" (unknown).
    # The combined extract+plan call only runs when the LLM extractor hasn't.
    structured_source: str = ""
    layout_plan: dict | None = None
    # Derived workspace packet (dict form) for handoff / visual planning
    workspace_packet: dict | None = None
    # Soft boosts from recent visual_interaction events {affordance: score}.
    # Populated by the planner when a DB session is available.
    interaction_boosts: dict[str, float] | None = None