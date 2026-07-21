"""Phase A — structured handoff validation and resolution."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.visual_summary.handoff.extract import (
    handoff_error_message,
    normalize_structured_content,
    resolve_structured_content,
    validate_handoff,
)
from app.visual_summary.handoff.structured import extract_structured_content

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


def test_normalize_preserves_process_flow_and_interaction_sequence():
    raw = {
        "summary": "The event loop coordinates async work.",
        "key_points": ["Stack runs sync code first"],
        "process_flow": {
            "nodes": [
                {"id": "call_stack", "label": "**Call Stack**", "detail": "`foo()` runs"},
                {"id": "web_api", "label": "Web APIs"},
                {"id": "queue", "label": "Callback Queue"},
            ],
            "edges": [
                {"source": "call_stack", "target": "web_api", "label": "setTimeout"},
                {"source": "web_api", "target": "queue", "label": "ready"},
                {"source": "queue", "target": "missing", "label": "orphan"},
            ],
        },
        "interaction_sequence": {
            "actors": ["Call Stack", "Web APIs"],
            "messages": [
                {
                    "source": "Call Stack",
                    "target": "Web APIs",
                    "label": "setTimeout",
                    "order": 0,
                    "note": "Timer registered",
                },
                {
                    "source": "Web APIs",
                    "target": "Call Stack",
                    "label": "callback",
                    "order": 1,
                },
            ],
        },
    }
    out = normalize_structured_content(raw)
    assert "process_flow" in out
    assert len(out["process_flow"]["nodes"]) == 3
    assert out["process_flow"]["nodes"][0]["label"] == "Call Stack"
    assert out["process_flow"]["nodes"][0]["detail"] == "`foo()` runs"
    # Orphan edge to unknown node dropped
    assert len(out["process_flow"]["edges"]) == 2
    assert "interaction_sequence" in out
    assert len(out["interaction_sequence"]["actors"]) == 2
    assert len(out["interaction_sequence"]["messages"]) == 2


def test_normalize_drops_empty_diagram_modules():
    out = normalize_structured_content(
        {
            "summary": "Thin answer",
            "key_points": ["a"],
            "process_flow": {"nodes": [], "edges": []},
            "interaction_sequence": {"actors": [], "messages": []},
        }
    )
    assert "process_flow" not in out
    assert "interaction_sequence" not in out


def test_resolve_structured_content_uses_heuristic_when_llm_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.visual_summary.handoff.extract.settings.visual_summary_llm_extractor", False
    )
    structured, source = resolve_structured_content(SAMPLE, goal="Summarize")
    assert source == "heuristic"
    assert structured["key_points"]


def _mock_llm(monkeypatch, payload: dict, captured: list | None = None):
    import json
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    class _FakeResp:
        choices = [SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=20)

    def fake_create(**kwargs):
        if captured is not None:
            captured.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.visual_summary.handoff.extract._client", lambda: fake_client)
    monkeypatch.setattr(
        "app.visual_summary.handoff.extract.settings.visual_summary_llm_extractor", True
    )
    monkeypatch.setattr(
        "app.visual_summary.handoff.extract.settings.openai_api_key", "sk-test"
    )
    # These tests cover the standalone extraction path — combined mode would
    # defer extraction to the planner and skip the call being mocked here.
    monkeypatch.setattr(
        "app.visual_summary.handoff.extract.settings.visual_summary_combined_call", False
    )


def test_resolve_structured_content_llm_primary_with_visual_fields(monkeypatch):
    llm_payload = {
        "summary": "React is strong; AWS depth is the main growth area.",
        "key_points": ["Shipped RAG features", "Led frontend platform work"],
        "levels": ["React | Strong", "AWS | Gap"],
        "matrix_rows": [
            "Requirement | Evidence | Status",
            "React | Lead role on two products | Strong",
        ],
        "priority_message": "AWS depth is the biggest gap for cloud-heavy roles.",
        "themes": ["frontend", "cloud"],
    }
    _mock_llm(monkeypatch, llm_payload)
    structured, source = resolve_structured_content(SAMPLE, goal="Assess my readiness")
    assert source == "llm"
    assert structured["levels"] == ["React | Strong", "AWS | Gap"]
    assert structured["matrix_rows"][0].startswith("Requirement")
    assert structured["priority_message"].startswith("AWS depth")
    # Heuristic fills fields the LLM left empty (merge, not replace).
    assert structured["sections"] or structured["key_points"]


def test_resolve_structured_content_merges_heuristic_gap_fill(monkeypatch):
    step_answer = """\
Here is the plan:

### Steps
1. **Audit your resume**:
   - Compare against three job posts.
2. **Rewrite the summary**:
   - Lead with shipped outcomes.
3. **Collect feedback**:
   - Ask two senior peers.
"""
    llm_payload = {
        "summary": "A three-step plan to sharpen the resume.",
        "key_points": ["Audit against job posts", "Lead with outcomes"],
        # LLM omitted ordered_actions — the heuristic found them.
    }
    _mock_llm(monkeypatch, llm_payload)
    structured, source = resolve_structured_content(step_answer, goal="how to improve")
    assert source == "llm"
    assert structured["summary"].startswith("A three-step plan")
    assert any(a.startswith("Audit your resume") for a in structured["ordered_actions"])


def test_llm_extraction_prompt_includes_evidence(monkeypatch):
    from app.visual_summary.handoff.evidence import AgentEvidenceBundle, DocumentEvidenceHit

    captured: list[str] = []
    _mock_llm(monkeypatch, {"summary": "Grounded overview of the workspace docs."}, captured)
    resolve_structured_content(
        SAMPLE,
        goal="Summarize",
        evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(filename="resume.pdf", snippet="Built RAG agent at scale.")
            ]
        ),
    )
    assert captured
    assert "resume.pdf" in captured[0]
    assert "Built RAG agent at scale." in captured[0]
    assert "levels" in captured[0]  # full visual schema requested


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
        "app.visual_summary.handoff.extract.extract_structured_content",
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
    monkeypatch.setattr("app.visual_summary.handoff.extract._client", lambda: fake_client)

    structured, source = resolve_structured_content(thin, goal="Explain docs")
    assert source == "llm"
    ok, _ = validate_handoff(structured)
    assert ok is True


def test_handoff_error_message_joins_errors():
    msg = handoff_error_message(["a", "b"])
    assert "a" in msg and "b" in msg