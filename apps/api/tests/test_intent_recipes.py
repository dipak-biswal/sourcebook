"""Intent → UI recipes and option_cards assembly."""

from app.agents.visual_summary.planning.intent_recipes import (
    RECIPE_COMPARISON,
    RECIPE_MECHANISM,
    RECIPE_STUDY_FULL,
    RECIPE_TRADEOFFS,
    apply_recipe_to_study_outline,
    content_contract_for_prompt,
    resolve_recipe,
)
from app.agents.visual_summary.planning.study_sheet import (
    build_topic_study_sheet_plan,
    infer_section_block_type,
)
from app.agents.visual_summary.render.assemble import assemble_block, assemble_blocks
from app.agents.visual_summary.handoff.structured import extract_structured_content


def test_resolve_recipe_from_goal_and_prefs():
    assert resolve_recipe(goal="How does the outbox pattern work?")["id"] == RECIPE_MECHANISM
    assert resolve_recipe(goal="Compare Kafka vs RabbitMQ")["id"] == RECIPE_COMPARISON
    assert (
        resolve_recipe(
            goal="Outbox",
            topic_title="Outbox Pattern",
            preferences={"focus": ["tradeoffs"]},
        )["id"]
        == RECIPE_TRADEOFFS
    )
    assert (
        resolve_recipe(
            goal="study sheet",
            topic_title="Load balancer",
            preferences={"format": ["study_sheet", "diagrams"]},
        )["id"]
        == RECIPE_STUDY_FULL
    )


def test_content_contract_mentions_concrete_rules():
    recipe = resolve_recipe(goal="Create a complete study sheet for Outbox")
    text = content_contract_for_prompt(recipe)
    assert "VISUAL / CONTENT CONTRACT" in text
    assert "Recipe:" in text
    assert "Required section arc" in text
    assert "Hard rules" in text


def test_recipe_does_not_reorder_study_panels():
    outline = [
        {"type": "key_points", "title": "1. Why", "panel_index": 1},
        {"type": "flow_diagram", "title": "2. Flow", "panel_index": 2},
        {"type": "table", "title": "3. Schema", "panel_index": 3},
    ]
    recipe = resolve_recipe(goal="study sheet for X")
    out = apply_recipe_to_study_outline(outline, recipe)
    assert [e["title"] for e in out] == ["1. Why", "2. Flow", "3. Schema"]
    assert all(e.get("recipe") == recipe["id"] for e in out)


def test_infer_options_section_as_option_cards():
    assert (
        infer_section_block_type(
            {
                "heading": "5. Outbox Processor Options",
                "bullets": [
                    "Polling publisher: query PENDING rows every few seconds",
                    "CDC: capture WAL changes and publish",
                ],
            }
        )
        == "option_cards"
    )
    assert (
        infer_section_block_type(
            {
                "heading": "Flight options",
                "body": "Airline | Tag | Price | Meta\nDelta | Cheapest | $212 | 6h nonstop\nUnited | Fastest | $289 | 5h 40m",
            }
        )
        == "option_cards"
    )


def test_assemble_option_cards_from_pipe_rows():
    block = assemble_block(
        {
            "type": "option_cards",
            "title": "Flights",
            "source_hint": "option_cards",
            "section_index": 1,
        },
        {
            "sections": [
                {
                    "heading": "1. Flights",
                    "body": (
                        "Carrier | Tag | Price | Detail\n"
                        "Delta | Cheapest | $212 | 6h 05m nonstop\n"
                        "United | Fastest | $289 | 5h 40m nonstop"
                    ),
                }
            ]
        },
    )
    assert block is not None
    assert block.type == "option_cards"
    assert block.items and len(block.items) >= 2
    assert any("$212" in i for i in block.items)


def test_assemble_option_cards_from_bullets():
    block = assemble_block(
        {
            "type": "option_cards",
            "title": "5. Options",
            "source_hint": "option_cards",
            "section_index": 1,
        },
        {
            "sections": [
                {
                    "heading": "5. Processor Options",
                    "bullets": [
                        "Polling publisher: query PENDING rows",
                        "CDC: capture log changes",
                    ],
                }
            ]
        },
    )
    assert block is not None
    assert block.type == "option_cards"
    assert block.items and len(block.items) >= 2


def test_study_sheet_includes_option_cards_for_options_section():
    answer = """
## 1. Why Outbox?
- Dual write problem loses messages.

## 2. High Level Flow
App → DB + Outbox → Processor → Broker → Consumer

## 3. Processor Options
Polling | Simple | 5s lag | Easy ops
CDC | Fast | <1s lag | More infra

## 4. Best Practices
- Index status
- Idempotent consumers
"""
    structured = extract_structured_content(
        answer,
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    plan = build_topic_study_sheet_plan(
        structured,
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    assert plan is not None
    types = [e["type"] for e in plan["block_outline"]]
    assert "option_cards" in types
    # Order preserved: Why first
    assert "Why" in plan["block_outline"][0]["title"] or "1." in plan["block_outline"][0]["title"]
    blocks, _dropped = assemble_blocks(plan["block_outline"], structured)
    assert any(b.type == "option_cards" for b in blocks)
