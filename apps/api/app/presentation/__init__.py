"""Generative UI presentation layer (planner + engine)."""

from app.presentation.engine import build_presentation
from app.presentation.planner import should_render_presentation

__all__ = ["build_presentation", "should_render_presentation"]