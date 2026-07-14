"""Input bundle for the presentation engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


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