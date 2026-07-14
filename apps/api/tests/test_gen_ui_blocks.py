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


def test_table_object_rows():
    norm = _normalize_block_dict(
        {
            "type": "table",
            "title": "Skills",
            "rows": [
                {"Skill": "React", "Level": "Strong"},
                {"Skill": "Python", "Level": "Expert"},
            ],
        }
    )
    assert norm is not None
    assert norm["type"] == "table"
    assert norm["items"][0] == "Skill | Level"
    assert norm["items"][1] == "React | Strong"
    assert norm["items"][2] == "Python | Expert"


def test_table_markdown_body():
    norm = _normalize_block_dict(
        {
            "type": "table",
            "body": "| Skill | Level |\n| --- | --- |\n| React | Strong |",
        }
    )
    assert norm is not None
    assert len(norm["items"]) == 2
    assert "Skill" in norm["items"][0]
    assert "React" in norm["items"][1]


def test_progress_and_tags():
    norm = _normalize_block_dict(
        {
            "type": "skill_bar",
            "items": ["React | 85"],
            "tags": ["skills"],
        }
    )
    assert norm is not None
    assert norm["type"] == "progress"
    assert norm["tags"] == ["skills"]