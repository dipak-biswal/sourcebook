"""Generative UI block type normalization."""

from app.agents.gen_ui import _normalize_block_dict


def test_metrics_alias():
    norm = _normalize_block_dict({"type": "stats", "items": ["Years | 8"]})
    assert norm is not None
    assert norm["type"] == "metrics"


def test_timeline_alias():
    norm = _normalize_block_dict({"type": "career", "items": ["2020 | Role | Detail"]})
    assert norm is not None
    assert norm["type"] == "timeline"


def test_comparison_alias():
    norm = _normalize_block_dict({"type": "vs", "items": ["A | B"]})
    assert norm is not None
    assert norm["type"] == "comparison"