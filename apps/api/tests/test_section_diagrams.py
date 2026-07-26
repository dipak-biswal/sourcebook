"""author_section_diagrams: LLM decides per-section diagram need + Mermaid."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.agents.visual_summary.planning.section_diagrams as sd


def _resp(payload: dict):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=50, completion_tokens=30),
    )


SECTIONS = [
    (1, {"heading": "1. Binary Search Tree — Insert", "body": "Insert 5, 3, 8.", "bullets": []}),
    (2, {"heading": "2. Best Practices", "body": "Keep it balanced.", "bullets": ["Rebalance often"]}),
]


def test_author_section_diagrams_maps_needed_sections(monkeypatch):
    payload = {
        "sections": [
            {
                "section_index": 1,
                "needs_diagram": True,
                "diagram_kind": "tree",
                "mermaid": "flowchart TD\n  a[5] --> b[3]\n  a --> c[8]",
            },
            {
                "section_index": 2,
                "needs_diagram": False,
                "diagram_kind": "",
                "mermaid": "",
            },
        ]
    }

    def fake_chat_json(client, *, schema_name, **kwargs):
        assert schema_name == "section_diagrams"
        return _resp(payload)

    monkeypatch.setattr(sd, "chat_json", fake_chat_json)
    monkeypatch.setattr(sd, "_client", lambda: MagicMock())

    out = sd.author_section_diagrams(SECTIONS, goal="Teach me BSTs")
    assert set(out.keys()) == {1}
    assert out[1]["diagram_kind"] == "tree"
    assert "flowchart TD" in out[1]["mermaid"]


def test_author_section_diagrams_empty_when_llm_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(sd, "chat_json", boom)
    monkeypatch.setattr(sd, "_client", lambda: MagicMock())

    out = sd.author_section_diagrams(SECTIONS, goal="Teach me BSTs")
    assert out == {}


def test_author_section_diagrams_ignores_unknown_index(monkeypatch):
    payload = {
        "sections": [
            {
                "section_index": 99,
                "needs_diagram": True,
                "diagram_kind": "tree",
                "mermaid": "flowchart TD\n  a-->b",
            },
        ]
    }

    def fake_chat_json(client, *, schema_name, **kwargs):
        return _resp(payload)

    monkeypatch.setattr(sd, "chat_json", fake_chat_json)
    monkeypatch.setattr(sd, "_client", lambda: MagicMock())

    out = sd.author_section_diagrams(SECTIONS, goal="Teach me BSTs")
    assert out == {}


def test_author_section_diagrams_empty_sections_short_circuits(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not call the LLM with no sections")

    monkeypatch.setattr(sd, "chat_json", boom)
    out = sd.author_section_diagrams([], goal="anything")
    assert out == {}
