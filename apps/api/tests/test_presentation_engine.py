"""Plan-driven render engine prompt and model selection."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.presentation.context import PresentationContext
from app.presentation.engine import build_presentation
from app.presentation.evidence import AgentEvidenceBundle, DocumentEvidenceHit
from app.presentation.structured import extract_structured_content

SAMPLE_ANSWER = """\
This workspace covers full-stack AI developer positioning.

## Key Points
- Shipped RAG pipelines with eval harnesses
- TypeScript/React and Python/FastAPI production experience

## FAQ
**Q: What stack should I emphasize?**
A: Lead with shipped LLM features, then TypeScript/React and FastAPI.
"""

JOB_SEARCH_GOAL = (
    'Explain the documents in the "Job Search" workspace '
    "(Targeting full-stack AI developer roles) with key points and a short FAQ."
)


def test_plan_driven_render_uses_slim_prompt_and_skips_rag(monkeypatch):
    structured = extract_structured_content(SAMPLE_ANSWER, goal=JOB_SEARCH_GOAL)
    layout_plan = {
        "presentation_profile": "concept_guide",
        "components": ["key_points", "faq"],
        "block_outline": [
            {"type": "key_points", "title": "Highlights", "purpose": "bullets"},
            {"type": "faq", "title": "FAQ", "purpose": "common questions"},
        ],
        "rationale": "Key points plus short FAQ.",
    }
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal=JOB_SEARCH_GOAL,
        final_answer=SAMPLE_ANSWER,
        workspace_name="Job Search",
        structured_content=structured,
        layout_plan=layout_plan,
        agent_evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(filename="resume.pdf", snippet="Built RAG agent.")
            ]
        ),
    )

    rag_called = {"count": 0}

    def fake_retrieve(*_args, **_kwargs):
        rag_called["count"] += 1
        return []

    captured: list[dict] = []

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "title": "Job Search",
                            "plain_summary": structured["summary"],
                            "presentation_profile": "concept_guide",
                            "blocks": [
                                {
                                    "type": "key_points",
                                    "title": "Highlights",
                                    "items": structured["key_points"][:2],
                                },
                                {
                                    "type": "faq",
                                    "title": "FAQ",
                                    "faqs": structured["faq"][:1],
                                },
                            ],
                        }
                    )
                )
            )
        ]
        usage = SimpleNamespace(prompt_tokens=120, completion_tokens=80, total_tokens=200)

    def fake_create(**kwargs):
        captured.append(kwargs)
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.presentation.engine.retrieve_chunks", fake_retrieve)
    monkeypatch.setattr("app.presentation.engine._client", lambda: fake_client)

    db = MagicMock()
    db.commit = MagicMock()

    spec, meta = build_presentation(db, ctx)

    assert rag_called["count"] == 0
    assert spec.get("error") is None
    assert meta["model"] == "gpt-4o-mini"
    prompt = captured[0]["messages"][1]["content"]
    assert "APPROVED LAYOUT PLAN" in prompt
    assert "STRUCTURED CONTENT" in prompt
    assert "EXCERPTS" not in prompt
    assert JOB_SEARCH_GOAL not in prompt
    assert "Targeting full-stack AI developer roles" not in prompt