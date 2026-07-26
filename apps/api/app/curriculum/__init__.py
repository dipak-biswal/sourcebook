"""Workspace curriculum: topic catalog, intake, and goal composition.

Modular package — not part of the main agent loop. Agents only consume the
composed goal + preference block after the user picks a topic.
"""

from app.curriculum.domain import is_curriculum_workspace
from app.curriculum.service import get_curriculum, save_curriculum

__all__ = [
    "is_curriculum_workspace",
    "get_curriculum",
    "save_curriculum",
]
