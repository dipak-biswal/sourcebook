"""Progressive Visual Summary: emit panels as they assemble (text-first, figure upgrade)."""

from app.agents.visual_summary.streaming.progressive import (
    FIGURE_BLOCK_TYPES,
    progressive_assemble_presentation,
    should_use_progressive_render,
)

__all__ = [
    "FIGURE_BLOCK_TYPES",
    "progressive_assemble_presentation",
    "should_use_progressive_render",
]
