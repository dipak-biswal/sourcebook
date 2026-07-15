"""Phase A — structured handoff validation and resolution."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.presentation.handoff import (
    handoff_error_message,
    normalize_structured_content,
    resolve_structured_content,
    validate_handoff,
)
from app.presentation.structured import extract_structured_content

SAMPLE = """\
## Summary
Strong React and FastAPI experience across shipped products.

## Key Points
- Built RAG pipelines with eval harnesses
- Led API design for multi-tenant workspaces
"""


def test_validate_handoff_accepts_summary_or_key_points_or_faq():
    structured = extract_structured_content(SAMPLE, goal="Summarize")
    ok, errors = validate_handoff(structured)
    assert ok is True
    assert errors == []


def test_validate_handoff_rejects_empty():
    ok, errors = validate_handoff({})
    assert ok is False
    assert any("too thin" in e.lower() for e in errors)


def test_normalize_structured_content_trims_and_caps():
    raw = {
        "summary": "  hello  ",
        "key_points": ["a", "a", "b"],
        "faq": [{"question": "Q?", "answer": "A"}],
        "sections": [{"heading": "H", "bullets": ["x"]}],
        "themes": ["t1"],
        "extra": "ignored",
    }
    out = normalize_structured_content(raw)
    assert out["summary"] == "hello"
    assert out["key_points"] == ["a", "b"]
    assert out["faq"][0]["question"] == "Q?"
    assert "extra" not in out


def test_resolve_structured_content_uses_heuristic_when_sufficient():
    structured, source = resolve_structured_content(SAMPLE, goal="Summarize")
    assert source == "heuristic"
    assert structured["key_points"]


def test_resolve_structured_content_upgrades_thin_via_llm(monkeypatch):
    import json

    thin = "Unstructured narrative without headings or bullets for heuristic parsing."
    llm_payload = {
        "summary": "Expanded summary with enough substance for layout planning.",
        "key_points": ["Point one", "Point two"],
        "faq": [],
        "sections": [],
        "themes": [],
    }

    monkeypatch.setattr(
        "app.presentation.handoff.extract_structured_content",
        lambda answer, goal="": {
            "summary": "",
            "key_points": [],
            "faq": [],
            "sections": [],
            "themes": [],
        },
    )

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(llm_payload))
            )
        ]
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=20)

    fake_client = MagicMock()
    fake_client.chat.completions.create = lambda **kwargs: _FakeResp()
    monkeypatch.setattr("app.presentation.handoff._client", lambda: fake_client)

    structured, source = resolve_structured_content(thin, goal="Explain docs")
    assert source == "llm"
    ok, _ = validate_handoff(structured)
    assert ok is True


def test_handoff_error_message_joins_errors():
    msg = handoff_error_message(["a", "b"])
    assert "a" in msg and "b" in msg