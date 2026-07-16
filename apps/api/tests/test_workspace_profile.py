"""LLM workspace profiler: fingerprint cache, validation, planner few-shot."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Workspace
from app.presentation.structured import format_plan_layout_prompt
from app.presentation.workspace_context import (
    derive_workspace_context,
    packet_from_dict,
    resolve_workspace_context,
)
from app.presentation.workspace_profile import (
    context_fingerprint,
    sanitize_planner_example,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


CHEF_PROFILE = {
    "domain_label": "cooking / personal recipe collection",
    "outcome_phrase": "cook better versions of saved recipes",
    "audience_phrase": "the home cook who owns the workspace",
    "success_criteria": "a clear method with quantities and timing",
    "tone": "instructional",
    "answer_sections": ["Overview", "Ingredients", "Method", "Tips"],
    "visual_affordances": ["ordered_guide", "concept_glossary", "metrics", "bogus"],
    "planner_example": {
        "presentation_profile": "recipe_card",
        "components": ["steps", "key_terms"],
        "block_outline": [
            {
                "type": "steps",
                "title": "Method",
                "source_hint": "ordered_actions",
                "width": "full",
                "purpose": "Cooking steps in order",
            },
            {
                "type": "key_terms",
                "title": "Ingredients",
                "source_hint": "concepts",
                "width": "half",
                "purpose": "Ingredient with amount",
            },
            {
                "type": "hologram",  # invalid — must be dropped
                "title": "Nope",
                "source_hint": "ordered_actions",
                "width": "full",
            },
        ],
        "rationale": "Recipe answers lead with the method.",
    },
}


def _mock_profiler(monkeypatch, payload: dict, calls: list | None = None):
    class _FakeResp:
        choices = [SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        usage = SimpleNamespace(prompt_tokens=60, completion_tokens=30)

    def fake_create(**kwargs):
        if calls is not None:
            calls.append(kwargs["messages"][1]["content"])
        return _FakeResp()

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(
        "app.presentation.workspace_profile._client", lambda: fake_client
    )
    monkeypatch.setattr(
        "app.presentation.workspace_profile.settings.workspace_llm_profiler", True
    )
    monkeypatch.setattr(
        "app.presentation.workspace_profile.settings.openai_api_key", "sk-test"
    )


def test_fingerprint_changes_with_inputs():
    base = dict(
        name="Recipes",
        description="Family recipe collection",
        tags=["cooking"],
        document_rows=[("carbonara.pdf", "ready")],
    )
    fp = context_fingerprint(**base)
    assert fp == context_fingerprint(**base)  # stable
    assert fp != context_fingerprint(**{**base, "description": "Now with baking"})
    assert fp != context_fingerprint(
        **{**base, "document_rows": [("carbonara.pdf", "ready"), ("pho.pdf", "ready")]}
    )
    # Pending docs don't affect the fingerprint until they are ready.
    assert fp == context_fingerprint(
        **{**base, "document_rows": [("carbonara.pdf", "ready"), ("pho.pdf", "queued")]}
    )


def test_sanitize_planner_example_drops_invalid_blocks():
    example = sanitize_planner_example(CHEF_PROFILE["planner_example"])
    assert example is not None
    types = [b["type"] for b in example["block_outline"]]
    assert types == ["steps", "key_terms"]
    assert example["presentation_profile"] == "recipe_card"
    assert example["components"] == ["steps", "key_terms"]
    # Fewer than 2 valid blocks → no example
    assert (
        sanitize_planner_example(
            {"block_outline": [{"type": "hologram", "source_hint": "faq"}]}
        )
        is None
    )


def test_sanitize_planner_example_repairs_aliases_and_hints():
    example = sanitize_planner_example(
        {
            "presentation_profile": "Recipe Card!",
            "block_outline": [
                # Alias type + off-menu hint → key_terms with canonical hint.
                {"type": "ingredients", "source_hint": "ingredient_list"},
                # Valid type, off-menu hint → repaired to the type's default.
                {"type": "steps", "source_hint": "cooking_steps"},
            ],
        }
    )
    assert example is not None
    assert example["block_outline"][0]["type"] == "key_terms"
    assert example["block_outline"][0]["source_hint"] == "concepts"
    assert example["block_outline"][1]["source_hint"] == "ordered_actions"
    assert example["presentation_profile"] == "recipe_card"


def test_resolve_profiles_once_then_serves_cache(monkeypatch, db_session):
    ws = Workspace(name="Recipes", description="Family recipe collection")
    db_session.add(ws)
    db_session.commit()

    calls: list[str] = []
    _mock_profiler(monkeypatch, CHEF_PROFILE, calls)

    packet = resolve_workspace_context(db_session, ws.id)
    assert len(calls) == 1
    assert packet.derived.domain_label.startswith("cooking")
    assert packet.derived.tone == "instructional"
    # Invalid affordance filtered; LLM ranking leads; heuristic extras kept.
    assert "bogus" not in packet.derived.visual_affordances
    assert packet.derived.visual_affordances[0] == "ordered_guide"
    assert "overview" in packet.derived.visual_affordances
    assert packet.derived.planner_example["presentation_profile"] == "recipe_card"
    assert ws.context_cache["fingerprint"]

    # Second resolve: cache hit, no new LLM call.
    again = resolve_workspace_context(db_session, ws.id)
    assert len(calls) == 1
    assert again.derived.domain_label == packet.derived.domain_label

    # Changing the description invalidates the fingerprint → re-profile.
    ws.description = "Recipes plus weekly meal planning"
    db_session.commit()
    resolve_workspace_context(db_session, ws.id)
    assert len(calls) == 2


def test_resolve_falls_back_to_heuristic_when_disabled(monkeypatch, db_session):
    ws = Workspace(name="Study Notes", description="Learn distributed systems")
    db_session.add(ws)
    db_session.commit()
    # Autouse conftest guard keeps the profiler off; no client mock needed.
    packet = resolve_workspace_context(db_session, ws.id)
    assert packet.derived.domain_label == ""
    assert "concept_glossary" in packet.derived.visual_affordances  # heuristic rule
    assert ws.context_cache is None  # nothing cached without a profile


def test_profiler_failure_returns_heuristic_uncached(monkeypatch, db_session):
    ws = Workspace(name="Recipes", description="Family recipe collection")
    db_session.add(ws)
    db_session.commit()

    fake_client = MagicMock()
    fake_client.chat.completions.create = MagicMock(side_effect=RuntimeError("down"))
    monkeypatch.setattr(
        "app.presentation.workspace_profile._client", lambda: fake_client
    )
    monkeypatch.setattr(
        "app.presentation.workspace_profile.settings.workspace_llm_profiler", True
    )
    monkeypatch.setattr(
        "app.presentation.workspace_profile.settings.openai_api_key", "sk-test"
    )

    packet = resolve_workspace_context(db_session, ws.id)
    assert packet.derived.domain_label == ""  # heuristic result
    assert ws.context_cache is None  # failure is retried next time, not cached


def test_packet_round_trips_through_dict():
    packet = derive_workspace_context(
        name="Recipes",
        description="Family recipe collection",
        tags=["cooking"],
        document_rows=[("carbonara.pdf", "ready")],
    )
    packet.derived.domain_label = "cooking"
    packet.derived.planner_example = {"presentation_profile": "recipe_card"}
    rebuilt = packet_from_dict(packet.to_dict())
    assert rebuilt.derived.domain_label == "cooking"
    assert rebuilt.derived.planner_example == {"presentation_profile": "recipe_card"}
    assert rebuilt.identity.name == "Recipes"
    assert rebuilt.evidence.documents_ready == ["carbonara.pdf"]


def test_planner_prompt_prefers_workspace_example():
    example = sanitize_planner_example(CHEF_PROFILE["planner_example"])
    prompt = format_plan_layout_prompt(
        {"user_goal": "how do I make this lighter?", "requested_components": []},
        layout_hints="",
        workspace_example=example,
    )
    assert "recipe_card" in prompt
    assert "resume_dashboard" not in prompt
    # Without an example, the static few-shot library is used.
    fallback = format_plan_layout_prompt(
        {"user_goal": "how do I make this lighter?", "requested_components": []},
        layout_hints="",
    )
    assert "EXAMPLE" in fallback
