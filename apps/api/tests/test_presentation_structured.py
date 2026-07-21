"""Structured content extraction for visual summary planning."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.visual_summary.tools import _plan_layout_llm
from app.visual_summary.context import PresentationContext
from app.visual_summary.handoff.evidence import AgentEvidenceBundle, DocumentEvidenceHit
from app.visual_summary.handoff.structured import (
    _BLOCK_MENU,
    _SOURCE_HINT_BLOCK_TYPE,
    build_plan_layout_input,
    extract_structured_content,
    format_plan_layout_prompt,
)


SAMPLE_ANSWER = """\
This workspace covers full-stack AI developer positioning.

## Key Points
- Shipped RAG pipelines with eval harnesses
- TypeScript/React and Python/FastAPI production experience
- Postgres + vector search in deployed products

## FAQ
**Q: What stack should I emphasize?**
A: Lead with shipped LLM features, then TypeScript/React and FastAPI.

**Q: What is weak?**
A: Generic AI enthusiasm without measurable outcomes.
"""


def test_extract_structured_content_parses_sections():
    structured = extract_structured_content(SAMPLE_ANSWER, goal="Explain with FAQ")
    assert "full-stack AI" in structured["summary"]
    assert any("RAG" in p for p in structured["key_points"])
    assert len(structured["faq"]) >= 2
    assert structured["faq"][0]["question"].endswith("?")


def test_promotes_q_numbered_sections_to_faq():
    answer = """\
Overview of the workspace documents.

**Q1: What roles should I target?**
- Full-stack AI developer roles with shipped LLM features.

**Q2: What stack to emphasize?**
- TypeScript/React, Python/FastAPI, Postgres, vector search.
"""
    structured = extract_structured_content(answer, goal="Explain with FAQ")
    questions = [item["question"] for item in structured["faq"]]
    assert len(structured["faq"]) >= 2
    assert any("roles" in q.lower() for q in questions)
    assert any("stack" in q.lower() for q in questions)


STEP_GUIDE_ANSWER = """\
Improving your resume is a critical step. Here's a step-by-step guide:

### Overview
Your resume should showcase skills and achievements relevant to target roles.

### Steps / Checklist

1. **Tailor Your Resume for Each Application**:
   - Review the job description carefully.
   - Highlight keywords and required skills.

2. **Quantify Achievements**:
   - Use metrics to demonstrate your impact.

3. **Seek Feedback**:
   - Share your resume with peers or mentors.

### FAQ / Self-Check
- **Is my resume tailored for the specific job?**
- **Have I quantified my achievements?**
- **Is the format clean and professional?**

### Next Steps
- Pick a job description and analyze it for keywords.
- Revise your resume using the checklist above.
"""


def test_step_guide_answer_extraction():
    structured = extract_structured_content(
        STEP_GUIDE_ANSWER, goal="how would i improve my resume step by step?"
    )
    # Overview section body becomes the summary (preamble is a colon lead-in).
    assert structured["summary"].startswith("Your resume should showcase")
    # Numbered bold labels become structured steps, not flattened sub-bullets.
    actions = structured["ordered_actions"]
    assert len(actions) == 3
    assert actions[0].startswith("Tailor Your Resume for Each Application — Review")
    assert actions[2].startswith("Seek Feedback — Share")
    # A self-check question list must not become a fake Q&A pair.
    assert structured["faq"] == []
    # Structural headings never leak into themes/chips.
    assert "Steps / Checklist" not in structured["themes"]
    assert "Next Steps" not in structured["themes"]


def test_faq_answer_not_fabricated_from_question_list():
    block = """\
### FAQ
- **Is my resume tailored for the job?**
- **Have I quantified my achievements?**

### Real FAQ
**What stack should I lead with?**
Lead with shipped LLM features and React.
"""
    structured = extract_structured_content(block, goal="faq")
    answers = [item["answer"] for item in structured["faq"]]
    assert all("Have I quantified" not in a for a in answers)
    assert any("shipped LLM features" in a for a in answers)


def test_plan_layout_prompt_uses_structured_input_not_raw_answer(monkeypatch):
    long_tail = "extra detail " * 500
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Explain documents with key points and FAQ",
        final_answer=SAMPLE_ANSWER + long_tail,
        structured_content=extract_structured_content(SAMPLE_ANSWER, goal="Explain"),
        agent_evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(filename="resume.pdf", snippet="Built RAG agent.")
            ]
        ),
    )

    captured: list[str] = []

    class _FakeResp:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"presentation_profile":"concept_guide","components":["faq","key_points"],"block_outline":[],"rationale":"ok"}'
                )
            )
        ]
        usage = SimpleNamespace(prompt_tokens=80, completion_tokens=20)

    def fake_create(**kwargs):
        captured.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr("app.visual_summary.tools._client", lambda: fake_client)

    result = _plan_layout_llm(ctx)
    prompt = captured[0]
    assert "STRUCTURED INPUT" in prompt
    assert '"structured_content"' in prompt or "structured_content" in prompt
    assert long_tail not in prompt
    assert result["structured_input"]["structured_content"]["key_points"]
    assert "resume.pdf" in format_plan_layout_prompt(
        build_plan_layout_input(
            goal=ctx.goal,
            structured_content=ctx.structured_content or {},
            evidence=ctx.agent_evidence,
            components=["faq"],
        ),
        layout_hints="hints",
    )


def test_block_menu_and_source_hint_map_include_diagram_types():
    assert "flow_diagram" in _BLOCK_MENU
    assert "sequence_diagram" in _BLOCK_MENU
    assert _SOURCE_HINT_BLOCK_TYPE["process_flow"] == "flow_diagram"
    assert _SOURCE_HINT_BLOCK_TYPE["interaction_sequence"] == "sequence_diagram"


def test_plan_layout_prompt_includes_diagram_grounding_rules():
    ctx_structured = extract_structured_content(SAMPLE_ANSWER, goal="Explain")
    prompt = format_plan_layout_prompt(
        build_plan_layout_input(
            goal="Explain",
            structured_content=ctx_structured,
            evidence=AgentEvidenceBundle(document_hits=[]),
            components=["key_points"],
        ),
        layout_hints="hints",
    )
    assert "flow_diagram" in prompt
    assert "sequence_diagram" in prompt
    assert "do not invent actors or steps" in prompt.lower()