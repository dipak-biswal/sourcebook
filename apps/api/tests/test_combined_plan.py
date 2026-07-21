"""Combined extract+plan call (#2) and strict json_schema outputs (#4)."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.agents.visual_summary.tools as vt
from app.agents.visual_summary.blocks.registry import ALL_BLOCK_TYPES, KNOWN_SOURCE_HINTS
from app.config import settings
from app.agents.visual_summary.context import PresentationContext
from app.agents.visual_summary.handoff.evidence import AgentEvidenceBundle
from app.agents.visual_summary.handoff.extract import (
    combined_extract_plan_enabled,
    format_combined_extract_plan_prompt,
    resolve_structured_content,
)
from app.agents.visual_summary.llm_json import PLAN_SCHEMA, chat_json

ANSWER = (
    "React and FastAPI are the core stack; RAG search shipped this quarter.\n\n"
    "- Shipped RAG features across workspaces\n"
    "- TypeScript frontend and Python API\n"
    "- Postgres with pgvector for retrieval\n"
)

COMBINED_PAYLOAD = {
    "structured_content": {
        "summary": "React and FastAPI are the core stack; RAG search shipped.",
        "key_points": ["Shipped RAG features", "TypeScript and Python"],
        "faq": [{"question": "What stack?", "answer": "React + FastAPI"}],
        "themes": ["rag", "stack"],
        "sections": [],
    },
    "layout_plan": {
        "presentation_profile": "stack_digest",
        "components": ["summary", "key_points"],
        "block_outline": [
            {
                "type": "summary",
                "title": "Overview",
                "purpose": "Stack overview",
                "source_hint": "summary",
                "width": "full",
            },
            {
                "type": "key_points",
                "title": "Highlights",
                "purpose": "Top facts",
                "source_hint": "key_points",
                "width": "half",
            },
        ],
        "rationale": "Summary-led digest.",
    },
}


def _resp(payload: dict):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=60),
    )


def _combined_flags(monkeypatch):
    monkeypatch.setattr(settings, "visual_summary_llm_extractor", True)
    monkeypatch.setattr(settings, "visual_summary_llm_planner", True)
    monkeypatch.setattr(settings, "visual_summary_combined_call", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")


def _ctx() -> PresentationContext:
    return PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize the workspace",
        final_answer=ANSWER,
        structured_content={
            "summary": "React and FastAPI are the core stack.",
            "key_points": ["Shipped RAG features"],
            "faq": [],
            "sections": [],
            "themes": [],
        },
        structured_source="heuristic",
        agent_evidence=AgentEvidenceBundle(),
    )


# --- resolve_structured_content gating ---


def test_combined_mode_skips_extraction_when_heuristic_has_substance(monkeypatch):
    _combined_flags(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("extraction LLM must not be called in combined mode")

    monkeypatch.setattr(
        "app.agents.visual_summary.handoff.extract.extract_structured_content_llm", boom
    )
    structured, source = resolve_structured_content(ANSWER, goal="Summarize")
    assert source == "heuristic"
    assert structured["key_points"]


def test_combined_mode_still_rescues_thin_heuristic(monkeypatch):
    _combined_flags(monkeypatch)
    monkeypatch.setattr(
        "app.agents.visual_summary.handoff.extract.extract_structured_content",
        lambda answer, goal="": {"summary": "", "key_points": [], "faq": [],
                                 "sections": [], "themes": []},
    )
    monkeypatch.setattr(
        "app.agents.visual_summary.handoff.extract.extract_structured_content_llm",
        lambda *a, **k: {
            "summary": "Expanded summary with substance.",
            "key_points": ["Point one", "Point two"],
            "faq": [], "sections": [], "themes": [],
        },
    )
    structured, source = resolve_structured_content(
        "Thin narrative without structure.", goal="Explain"
    )
    assert source == "llm"
    assert structured["key_points"]


def test_combined_disabled_when_any_flag_off(monkeypatch):
    _combined_flags(monkeypatch)
    assert combined_extract_plan_enabled() is True
    monkeypatch.setattr(settings, "visual_summary_combined_call", False)
    assert combined_extract_plan_enabled() is False
    monkeypatch.setattr(settings, "visual_summary_combined_call", True)
    monkeypatch.setattr(settings, "visual_summary_llm_extractor", False)
    assert combined_extract_plan_enabled() is False


# --- _plan_with_validation combined path ---


def test_plan_with_validation_uses_one_combined_call(monkeypatch):
    _combined_flags(monkeypatch)
    calls: list[str] = []

    def fake_chat_json(client, *, schema_name, **kwargs):
        calls.append(schema_name)
        return _resp(COMBINED_PAYLOAD)

    monkeypatch.setattr(vt, "chat_json", fake_chat_json)
    monkeypatch.setattr(vt, "_client", lambda: MagicMock())

    ctx = _ctx()
    result = vt._plan_with_validation(ctx)
    assert calls == ["extract_and_plan"]  # exactly one LLM call
    assert result["validation_status"] == "passed"
    assert result["planner_source"] == "combined"
    assert result["plan"]["presentation_profile"] == "stack_digest"
    # Context upgraded to the combined extraction
    assert ctx.structured_source == "llm"
    assert ctx.structured_content["faq"]
    assert result["structured_content"]["faq"]


def test_combined_invalid_plan_repairs_via_plan_only_call(monkeypatch):
    _combined_flags(monkeypatch)
    bad = json.loads(json.dumps(COMBINED_PAYLOAD))
    # levels has no data in structured_content → grounding validation fails
    bad["layout_plan"]["block_outline"].append(
        {
            "type": "progress",
            "title": "Levels",
            "purpose": "x",
            "source_hint": "levels",
            "width": "half",
        }
    )
    repair_plan = COMBINED_PAYLOAD["layout_plan"]
    responses = [_resp(bad), _resp(repair_plan)]
    calls: list[str] = []

    def fake_chat_json(client, *, schema_name, **kwargs):
        calls.append(schema_name)
        return responses.pop(0)

    monkeypatch.setattr(vt, "chat_json", fake_chat_json)
    monkeypatch.setattr(vt, "_client", lambda: MagicMock())

    result = vt._plan_with_validation(_ctx())
    assert calls == ["extract_and_plan", "layout_plan"]
    assert result["validation_status"] == "passed"
    assert result["replan_attempted"] is True
    assert result["planner_source"] == "llm"


def test_combined_call_failure_falls_back_to_two_call_path(monkeypatch):
    _combined_flags(monkeypatch)
    calls: list[str] = []

    def fake_chat_json(client, *, schema_name, **kwargs):
        calls.append(schema_name)
        if schema_name == "extract_and_plan":
            raise RuntimeError("provider down")
        return _resp(COMBINED_PAYLOAD["layout_plan"])

    monkeypatch.setattr(vt, "chat_json", fake_chat_json)
    monkeypatch.setattr(vt, "_client", lambda: MagicMock())

    result = vt._plan_with_validation(_ctx())
    assert calls[0] == "extract_and_plan"
    assert "layout_plan" in calls  # plan-only path took over
    assert result["validation_status"] == "passed"
    assert result["planner_source"] == "llm"


def test_combined_skipped_when_extraction_already_ran(monkeypatch):
    _combined_flags(monkeypatch)
    calls: list[str] = []

    def fake_chat_json(client, *, schema_name, **kwargs):
        calls.append(schema_name)
        return _resp(COMBINED_PAYLOAD["layout_plan"])

    monkeypatch.setattr(vt, "chat_json", fake_chat_json)
    monkeypatch.setattr(vt, "_client", lambda: MagicMock())

    ctx = _ctx()
    ctx.structured_source = "llm"  # extraction already happened
    vt._plan_with_validation(ctx)
    assert "extract_and_plan" not in calls


# --- chat_json strict-schema fallback ---


def test_chat_json_prefers_json_schema():
    captured: list[dict] = []
    client = MagicMock()

    def create(**kwargs):
        captured.append(kwargs)
        return _resp({})

    client.chat.completions.create = create
    chat_json(
        client,
        model="m",
        system="s",
        prompt="p",
        schema_name="layout_plan",
        schema=PLAN_SCHEMA,
    )
    rf = captured[0]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True


def test_chat_json_falls_back_to_json_object_when_rejected():
    captured: list[dict] = []
    client = MagicMock()

    def create(**kwargs):
        captured.append(kwargs)
        if kwargs["response_format"]["type"] == "json_schema":
            raise TypeError("response_format not supported")
        return _resp({})

    client.chat.completions.create = create
    chat_json(
        client,
        model="m",
        system="s",
        prompt="p",
        schema_name="layout_plan",
        schema=PLAN_SCHEMA,
    )
    assert [c["response_format"]["type"] for c in captured] == [
        "json_schema",
        "json_object",
    ]


def test_plan_schema_enums_derive_from_registry():
    outline_props = PLAN_SCHEMA["properties"]["block_outline"]["items"]["properties"]
    assert outline_props["type"]["enum"] == list(ALL_BLOCK_TYPES)
    assert outline_props["source_hint"]["enum"] == list(KNOWN_SOURCE_HINTS)


def test_combined_extract_plan_prompt_teaches_diagram_fields():
    """
    The combined extract+plan call is the default runtime path
    (combined_extract_plan_enabled() is True out of the box) — its own
    hand-written prompt, not structured.py's block menu, is what the model
    actually sees. Both the extraction shape and the plan rules must mention
    process_flow/interaction_sequence and their block types, or the model has
    no way to know these exist.
    """
    prompt = format_combined_extract_plan_prompt(
        "Some answer text long enough to matter here.",
        goal="Explain the mechanism",
    )
    assert "process_flow" in prompt
    assert "interaction_sequence" in prompt
    assert "flow_diagram" in prompt
    assert "sequence_diagram" in prompt
    assert "explain" in prompt.lower() or "mechanism" in prompt.lower()
    assert "mechanism_explainer" in prompt
    assert "LINEAR" in prompt or "linear" in prompt
    # Must not teach the model to emit the placeholder as the profile value
    assert '"presentation_profile": "short_snake_case"' not in prompt
