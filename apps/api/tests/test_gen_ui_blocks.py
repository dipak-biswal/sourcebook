"""Generative UI block type normalization."""

from app.visual_summary.blocks.gen_ui import _normalize_block_dict


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


def test_progress_data_alias_list():
    norm = _normalize_block_dict(
        {
            "type": "progress",
            "title": "Skills",
            "data": ["React | Strong", "Python | Gap"],
        }
    )
    assert norm is not None
    assert norm["items"] == ["React | Strong", "Python | Gap"]


def test_table_drops_markdown_separator_rows():
    norm = _normalize_block_dict(
        {
            "type": "table",
            "title": "Skills Overview",
            "items": [
                "Skill | Proficiency Level",
                "--------------------------- | -------------------",
                "React 18/19 | Strong",
            ],
        }
    )
    assert norm is not None
    assert len(norm["items"]) == 2
    assert not any("---" in row for row in norm["items"])


def test_progress_drops_separator_items():
    norm = _normalize_block_dict(
        {
            "type": "progress",
            "items": [
                "-------------------",
                "React 18/19 | Strong",
            ],
        }
    )
    assert norm is not None
    assert norm["items"] == ["React 18/19 | Strong"]


def test_table_strips_markdown_bold():
    norm = _normalize_block_dict(
        {
            "type": "table",
            "title": "Skills Overview",
            "data": (
                "| Skill | Level |\n"
                "| --- | --- |\n"
                "| **Frontend Development** | |\n"
                "| React 18/19 | Strong |"
            ),
        }
    )
    assert norm is not None
    assert any("Frontend Development" in row for row in norm["items"])
    assert not any("**" in row for row in norm["items"])


def test_faq_strips_numbered_markdown():
    norm = _normalize_block_dict(
        {
            "type": "faq",
            "faqs": [
                {
                    "question": "1. **What is your experience with AI?",
                    "answer": "- I have integrated AI features into applications.",
                }
            ],
        }
    )
    assert norm is not None
    assert norm["faqs"][0]["question"].startswith("What is your experience")
    assert "**" not in norm["faqs"][0]["question"]
    assert norm["faqs"][0]["answer"].startswith("I have integrated")


def test_table_data_markdown_string():
    norm = _normalize_block_dict(
        {
            "type": "table",
            "title": "Skills Overview",
            "data": (
                "| Skill | Level |\n"
                "| --- | --- |\n"
                "| React | Strong |\n"
                "| Python | Gap |"
            ),
        }
    )
    assert norm is not None
    assert norm["items"]
    assert any("React" in row for row in norm["items"])


def test_flow_diagram_alias():
    norm = _normalize_block_dict(
        {
            "type": "flowchart",
            "nodes": [{"id": "a", "label": "Call function"}, {"id": "b", "label": "Push to stack"}],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    assert norm is not None
    assert norm["type"] == "flow_diagram"
    assert len(norm["nodes"]) == 2
    assert len(norm["edges"]) == 1


def test_flow_diagram_drops_edge_with_unknown_node():
    norm = _normalize_block_dict(
        {
            "type": "flow_diagram",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "a", "target": "ghost"},
            ],
        }
    )
    assert norm is not None
    assert len(norm["edges"]) == 1
    assert norm["edges"][0]["target"] == "b"


def test_flow_diagram_too_few_nodes_drops_block():
    norm = _normalize_block_dict(
        {
            "type": "flow_diagram",
            "nodes": [{"id": "a", "label": "A"}],
            "edges": [],
        }
    )
    assert norm is None


def test_flow_diagram_no_edges_drops_block():
    norm = _normalize_block_dict(
        {
            "type": "flow_diagram",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [],
        }
    )
    assert norm is None


def test_flow_diagram_keeps_detail_for_expand():
    norm = _normalize_block_dict(
        {
            "type": "flow_diagram",
            "nodes": [
                {"id": "a", "label": "A", "detail": "Example: foo()"},
                {"id": "b", "label": "B"},
            ],
            "edges": [{"source": "a", "target": "b", "label": "calls"}],
        }
    )
    assert norm is not None
    assert norm["nodes"][0]["detail"] == "Example: foo()"
    assert norm["edges"][0]["label"] == "calls"


def test_sequence_diagram_alias():
    norm = _normalize_block_dict(
        {
            "type": "uml_sequence",
            "actors": ["Call Stack", "Web APIs"],
            "messages": [
                {"source": "Call Stack", "target": "Web APIs", "label": "setTimeout()", "order": 0}
            ],
        }
    )
    assert norm is not None
    assert norm["type"] == "sequence_diagram"
    assert norm["actors"] == ["Call Stack", "Web APIs"]
    assert len(norm["messages"]) == 1


def test_sequence_diagram_auto_adds_missing_actor():
    norm = _normalize_block_dict(
        {
            "type": "sequence_diagram",
            "actors": ["Call Stack"],
            "messages": [
                {"source": "Call Stack", "target": "Callback Queue", "label": "enqueue", "order": 0}
            ],
        }
    )
    assert norm is not None
    assert "Callback Queue" in norm["actors"]


def test_sequence_diagram_missing_order_gets_index_assigned():
    norm = _normalize_block_dict(
        {
            "type": "sequence_diagram",
            "actors": ["A", "B"],
            "messages": [
                {"source": "A", "target": "B", "label": "first"},
                {"source": "B", "target": "A", "label": "second"},
            ],
        }
    )
    assert norm is not None
    assert [m["order"] for m in norm["messages"]] == [0, 1]


def test_sequence_diagram_self_message_preserved():
    norm = _normalize_block_dict(
        {
            "type": "sequence_diagram",
            "actors": ["Event Loop", "Call Stack"],
            "messages": [
                {"source": "Event Loop", "target": "Event Loop", "label": "tick", "order": 0},
                {"source": "Event Loop", "target": "Call Stack", "label": "run", "order": 1},
            ],
        }
    )
    assert norm is not None
    self_msg = next(m for m in norm["messages"] if m["label"] == "tick")
    assert self_msg["source"] == self_msg["target"] == "Event Loop"


def test_sequence_diagram_too_few_actors_drops_block():
    norm = _normalize_block_dict(
        {
            "type": "sequence_diagram",
            "actors": ["A"],
            "messages": [{"source": "A", "target": "A", "label": "noop", "order": 0}],
        }
    )
    assert norm is None