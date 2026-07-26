"""Early visual paint from streamed study sections (parallel with main answer)."""

from unittest.mock import MagicMock

from app.agents.main.runner.early_visual import (
    early_visual_is_ready,
    refresh_early_visual,
    _structured_from_streamed,
)
from app.models import AgentRun
import uuid


def test_structured_from_streamed():
    sections = [
        {"heading": "1. Why", "body": "Because", "bullets": ["a"]},
        {"heading": "2. Flow", "body": "A → B → C", "bullets": []},
    ]
    s = _structured_from_streamed(sections, "study sheet")
    assert len(s["sections"]) == 2


def test_refresh_early_visual_emits_panels():
    run = AgentRun(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Create a complete study sheet for the Outbox Pattern",
        status="running",
        agent_type="general",
    )
    db = MagicMock()
    db.get.return_value = None
    events: list[tuple[str, dict]] = []

    sections = [
        {
            "heading": "1. Why Outbox?",
            "body": "Atomic dual-write.",
            "bullets": ["No message loss", "Eventual consistency"],
        },
        {
            "heading": "2. High Level Flow",
            "body": "Business → DB → Outbox → Publish → Consume",
            "bullets": ["Business op", "Write DB", "Outbox", "Publish"],
        },
        {
            "heading": "3. Without vs With",
            "body": "Without can lose messages.",
            "bullets": [
                "DB then publish | DB + outbox",
                "Message may be lost | Delivered eventually",
            ],
        },
    ]

    spec = refresh_early_visual(
        db,
        run,
        sections=sections,
        on_event=lambda k, p: events.append((k, p)),
        force_complete=True,
    )
    assert spec is not None
    assert (spec.get("blocks") or [])
    assert early_visual_is_ready(spec)
    kinds = [k for k, _ in events]
    assert "presentation_skeleton" in kinds
    assert "presentation_panel_ready" in kinds
    assert run.presentation_spec is not None


def test_enrich_early_visual_skips_without_mcp(monkeypatch):
    from app.agents.main.runner.early_visual import enrich_early_visual_with_mcp

    run = AgentRun(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="study sheet",
        status="completed",
        agent_type="general",
        presentation_spec={
            "type": "generative_ui",
            "blocks": [{"type": "key_points", "tags": ["__section:1"]}],
            "early_visual": True,
        },
        run_options={"enabled_mcp_ids": []},
    )
    db = MagicMock()
    assert enrich_early_visual_with_mcp(db, run) == 0
