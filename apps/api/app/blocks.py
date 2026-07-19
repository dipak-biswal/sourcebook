"""Single source of truth for generative UI block types.

Every consumer derives from BLOCK_SPECS:
- gen_ui.BlockType Literal (kept static for typing; a registry test pins it)
- plan_validator.ALLOWED_BLOCK_TYPES
- ui_intent affordance/source-hint maps and KNOWN_SOURCE_HINTS order
- render_blocks width defaults
- the web contract (apps/web/src/components/agents/block-contract.ts,
  regenerated via scripts/export_block_contract.py; a drift test enforces it)

To add a block type: add a BlockSpec here, extend the BlockType Literal in
gen_ui.py, add a renderer case in the web's GenerativeUI.tsx, and run
scripts/export_block_contract.py. The registry tests fail until all match.

Ordering matters: specs with a source_hint define the display order of
KNOWN_SOURCE_HINTS in planner prompts and validator messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Width = Literal["full", "half", "promote"]


@dataclass(frozen=True)
class BlockSpec:
    type: str
    default_title: str
    # Structured-content field this block fills from (None = free-form).
    source_hint: str | None = None
    # UiIntent affordance driving eligibility/scoring (None = not intent-planned).
    affordance: str | None = None
    # True when this block is the primary renderer for its affordance
    # (comparison_matrix prefers a table; the comparison block is its alt).
    primary_for_affordance: bool = True
    # "full"/"half" grid width; "promote" = half until it holds many rows.
    width: Width = "half"


BLOCK_SPECS: tuple[BlockSpec, ...] = (
    BlockSpec("summary", "Overview", "summary", "overview", width="full"),
    BlockSpec("key_points", "Key points", "key_points", "highlights", width="half"),
    BlockSpec("key_terms", "Core concepts", "concepts", "concept_glossary", width="promote"),
    BlockSpec("steps", "Steps", "ordered_actions", "ordered_guide", width="full"),
    BlockSpec("table", "Comparison", "matrix_rows", "comparison_matrix", width="full"),
    BlockSpec(
        "comparison",
        "Tradeoffs",
        "comparisons",
        "comparison_matrix",
        primary_for_affordance=False,
        width="full",
    ),
    BlockSpec("progress", "Levels", "levels", "qualitative_levels", width="promote"),
    BlockSpec("faq", "FAQ", "faq", "self_check", width="half"),
    BlockSpec("callout", "Priority", "priority_message", "priority_alert", width="half"),
    BlockSpec("chips", "Themes", "themes", "topic_filter", width="full"),
    BlockSpec("timeline", "Timeline", "milestones", "timeline", width="full"),
    BlockSpec("metrics", "Metrics", "metrics", "metrics", width="promote"),
    BlockSpec("quote", "Quote", width="half"),
    BlockSpec("chart", "Chart", width="full"),
)

ALL_BLOCK_TYPES: tuple[str, ...] = tuple(s.type for s in BLOCK_SPECS)
BLOCK_TYPE_SET: frozenset[str] = frozenset(ALL_BLOCK_TYPES)

# source_hint values in registry order — the planner whitelist display order.
KNOWN_SOURCE_HINTS: tuple[str, ...] = tuple(
    s.source_hint for s in BLOCK_SPECS if s.source_hint
)

# affordance → (block_type, source_hint, default_title) for primary renderers.
AFFORDANCE_SPEC: dict[str, tuple[str, str, str]] = {
    s.affordance: (s.type, s.source_hint or "", s.default_title)
    for s in BLOCK_SPECS
    if s.affordance and s.primary_for_affordance
}

# source_hint → affordance used for data-presence checks.
SOURCE_HINT_AFFORDANCE: dict[str, str] = {
    s.source_hint: s.affordance
    for s in BLOCK_SPECS
    if s.source_hint and s.affordance
}

FULL_WIDTH_TYPES: frozenset[str] = frozenset(
    s.type for s in BLOCK_SPECS if s.width == "full"
)
WIDTH_PROMOTE_TYPES: frozenset[str] = frozenset(
    s.type for s in BLOCK_SPECS if s.width == "promote"
)


def spec_for(block_type: str) -> BlockSpec | None:
    for s in BLOCK_SPECS:
        if s.type == block_type:
            return s
    return None


def web_contract() -> dict:
    """Contract exported to the web app (block-contract.ts)."""
    return {
        "version": 1,
        "block_types": list(ALL_BLOCK_TYPES),
        "source_hints": list(KNOWN_SOURCE_HINTS),
        "widths": {s.type: s.width for s in BLOCK_SPECS},
    }
