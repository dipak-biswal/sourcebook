"""Topic study-sheet layout planning and assembly."""

from app.agents.visual_summary.planning.study_sheet import (
    STUDY_SHEET_PROFILE,
    build_topic_study_sheet_plan,
    infer_section_block_type,
    is_topic_study_sheet_goal,
    should_use_topic_study_sheet,
)
from app.agents.visual_summary.render.assemble import assemble_blocks
from app.agents.visual_summary.handoff.structured import extract_structured_content


def test_goal_detection():
    assert is_topic_study_sheet_goal(
        "Create a complete study sheet for the Outbox Pattern"
    )
    assert is_topic_study_sheet_goal("Teach me outbox with end-to-end example")
    assert not is_topic_study_sheet_goal("List documents in this workspace")


def test_infer_section_types():
    assert (
        infer_section_block_type(
            {
                "heading": "3. Without vs With Outbox",
                "bullets": ["Update DB | Publish | Risk", "A | B | C"],
            }
        )
        == "comparison"
    )
    assert (
        infer_section_block_type(
            {
                "heading": "4. Database Outbox Table",
                "body": "id | status | payload\n1 | PENDING | {}",
            }
        )
        == "table"
    )
    assert (
        infer_section_block_type(
            {
                "heading": "2. High Level Flow",
                "body": "1. Write DB\n2. Outbox\n3. Publish",
            }
        )
        == "flow_diagram"
    )
    assert (
        infer_section_block_type(
            {
                "heading": "9. Best Practices",
                "bullets": ["Index status", "Idempotent consumers", "Monitor failures"],
            }
        )
        == "key_points"
    )


def _outbox_answer() -> str:
    return """
## 1. Why Outbox Pattern?
- Distributed systems rely on messages.
- Without outbox, failures between commit and publish lose messages.
- Outbox ensures atomicity.

## 2. Outbox Pattern – High Level Flow
1. Business operation
2. Write to database
3. Write to outbox table
4. Outbox processor publishes
5. Message consumed by service B

## 3. Without vs With Outbox Pattern
Without | With
DB then publish (can lose) | DB + outbox in one txn
Message may be lost | Eventually delivered

## 4. Database Outbox Table Example
id | aggregate_id | event_type | status
1 | 1001 | OrderCreated | PENDING
2 | 1002 | OrderPaid | PENDING

## 5. Outbox Processor Options
- Polling publisher: query PENDING rows
- CDC: capture log changes

## 6. Consumer Side
1. Consume from broker
2. Process idempotently
3. Handle duplicates

## 7. Transaction Boundaries
1. BEGIN TRANSACTION
2. Update business tables
3. Insert outbox message
4. COMMIT

## 8. Failure Scenarios & Recovery
Failure Point | Problem | Handling
After commit before publish | Message may be lost | Processor retries later
Processor crash | Not published | Resume PENDING

## 9. Best Practices
- Store minimal payload
- Index status and created_at
- Use idempotent consumers
- Monitor failed messages

## 10. End-to-End Example
User Order → Order Service → Outbox Processor → Broker → Notification Service

## 11. When to Use Outbox Pattern?
- Services communicate via events
- Need guaranteed delivery
- Eventual consistency is OK

## 12. Summary
- Solves dual-write problem
- Write data + message in one DB transaction
- Publish asynchronously
"""


def test_study_sheet_plan_from_numbered_answer():
    structured = extract_structured_content(
        _outbox_answer(),
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    assert should_use_topic_study_sheet(
        goal="Create a complete study sheet for the Outbox Pattern",
        structured=structured,
    )
    plan = build_topic_study_sheet_plan(
        structured,
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    assert plan is not None
    assert plan["presentation_profile"] == STUDY_SHEET_PROFILE
    outline = plan["block_outline"]
    assert len(outline) >= 8
    assert all(e.get("width") == "full" for e in outline)
    assert all(e.get("section_index") for e in outline)
    # Order preserved — first panel about "Why"
    assert "Why" in outline[0]["title"] or "1." in outline[0]["title"]


def test_assemble_study_sheet_panels():
    structured = extract_structured_content(
        _outbox_answer(),
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    plan = build_topic_study_sheet_plan(
        structured,
        goal="Create a complete study sheet for the Outbox Pattern",
    )
    assert plan is not None
    blocks, dropped = assemble_blocks(plan["block_outline"], structured)
    assert len(blocks) >= 6, (len(blocks), dropped, [b.type for b in blocks])
    assert all(b.width == "full" for b in blocks)
    # Panel chrome tags present
    assert any(
        any(t.startswith("__section:") for t in (b.tags or [])) for b in blocks
    )


def test_non_teaching_goal_skips_study_sheet():
    structured = extract_structured_content(
        "Here is a short note about CAP.\n\n## Overview\nCAP is about tradeoffs.",
        goal="What is CAP theorem?",
    )
    plan = build_topic_study_sheet_plan(
        structured, goal="What is CAP theorem?"
    )
    # Too few real sections / not a study-sheet goal
    assert plan is None
