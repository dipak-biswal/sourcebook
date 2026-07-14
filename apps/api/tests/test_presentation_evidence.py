"""Agent evidence bundle for presentation engine."""

from app.presentation.evidence import (
    collect_evidence_from_steps,
    format_agent_evidence,
)


def test_collect_evidence_from_search_and_web_steps():
    steps = [
        {
            "step_index": 1,
            "type": "tool_result",
            "tool_name": "search_documents",
            "output": [
                {
                    "chunk_id": "c1",
                    "filename": "Resume.pdf",
                    "snippet": "Built RAG chatbot with FastAPI and React.",
                    "score": 0.91,
                }
            ],
        },
        {
            "step_index": 2,
            "type": "tool_result",
            "tool_name": "web_search",
            "output": {
                "query": "senior full stack AI engineer skills 2026",
                "results": [
                    {
                        "title": "Senior AI Engineer Skills",
                        "url": "https://example.com/skills",
                        "snippet": "React, Python, LLM APIs, and deployment.",
                    }
                ],
            },
        },
        {
            "step_index": 3,
            "type": "final",
            "output": "Answer text",
        },
    ]
    bundle = collect_evidence_from_steps(steps)
    assert len(bundle.document_hits) == 1
    assert bundle.document_hits[0].filename == "Resume.pdf"
    assert "RAG chatbot" in bundle.document_hits[0].snippet
    assert len(bundle.web_hits) == 1
    assert bundle.web_hits[0].title == "Senior AI Engineer Skills"
    assert bundle.has_content() is True


def test_collect_evidence_dedupes_repeated_hits():
    hit = {
        "chunk_id": "c1",
        "filename": "Resume.pdf",
        "snippet": "Same snippet",
        "score": 0.9,
    }
    steps = [
        {"step_index": 1, "type": "tool_result", "tool_name": "search_documents", "output": [hit]},
        {"step_index": 2, "type": "tool_result", "tool_name": "search_documents", "output": [hit]},
    ]
    bundle = collect_evidence_from_steps(steps)
    assert len(bundle.document_hits) == 1


def test_format_agent_evidence_includes_doc_and_web_sections():
    steps = [
        {
            "step_index": 1,
            "type": "tool_result",
            "tool_name": "search_documents",
            "output": [
                {"filename": "Resume.pdf", "snippet": "Led React and FastAPI delivery."}
            ],
        },
        {
            "step_index": 2,
            "type": "tool_result",
            "tool_name": "web_search",
            "output": {
                "results": [
                    {
                        "title": "AI role requirements",
                        "url": "https://example.com",
                        "snippet": "Expect LLM integration experience.",
                    }
                ]
            },
        },
    ]
    text = format_agent_evidence(collect_evidence_from_steps(steps))
    assert "AGENT TOOL EVIDENCE" in text
    assert "[doc-1]" in text
    assert "Resume.pdf" in text
    assert "React and FastAPI" in text
    assert "[web-1]" in text
    assert "LLM integration" in text


def test_format_agent_evidence_empty_bundle():
    assert format_agent_evidence(collect_evidence_from_steps([])) == ""