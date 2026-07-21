"""Block registry is the single source of truth — drift fails here."""

from pathlib import Path
from typing import get_args

from app.agents.visual_summary.blocks.gen_ui import BlockType
from app.agents.visual_summary.blocks.registry import (
    AFFORDANCE_SPEC,
    ALL_BLOCK_TYPES,
    BLOCK_TYPE_SET,
    KNOWN_SOURCE_HINTS,
    SOURCE_HINT_AFFORDANCE,
)
from app.agents.visual_summary.planning.plan_validator import ALLOWED_BLOCK_TYPES


def test_gen_ui_literal_matches_registry():
    assert set(get_args(BlockType)) == BLOCK_TYPE_SET


def test_validator_allows_exactly_registry_types():
    assert ALLOWED_BLOCK_TYPES == BLOCK_TYPE_SET


def test_source_hints_are_unique_and_mapped():
    assert len(KNOWN_SOURCE_HINTS) == len(set(KNOWN_SOURCE_HINTS))
    for hint in KNOWN_SOURCE_HINTS:
        assert hint in SOURCE_HINT_AFFORDANCE, hint


def test_affordances_reference_registry_types():
    for affordance, (btype, hint, title) in AFFORDANCE_SPEC.items():
        assert btype in BLOCK_TYPE_SET, affordance
        assert hint in KNOWN_SOURCE_HINTS, affordance
        assert title


def test_web_contract_file_matches_registry():
    """The generated block-contract.ts must be regenerated when the registry
    changes: uv run python scripts/export_block_contract.py"""
    import sys

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        from export_block_contract import CONTRACT_PATH, render_contract_ts
    finally:
        sys.path.remove(str(scripts_dir))

    assert CONTRACT_PATH.exists(), (
        f"missing {CONTRACT_PATH} — run scripts/export_block_contract.py"
    )
    assert CONTRACT_PATH.read_text() == render_contract_ts(), (
        "block-contract.ts is stale — run scripts/export_block_contract.py"
    )


def test_web_renderer_has_case_for_every_registry_type():
    """GenerativeUI.tsx must switch on every registry block type."""
    tsx = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "web"
        / "src"
        / "components"
        / "agents"
        / "GenerativeUI.tsx"
    ).read_text()
    missing = [t for t in ALL_BLOCK_TYPES if f'case "{t}"' not in tsx]
    assert not missing, f"GenerativeUI.tsx missing renderer cases: {missing}"
