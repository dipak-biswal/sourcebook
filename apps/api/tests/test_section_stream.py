"""Main-agent section streaming (closed ## N. sections mid-answer)."""

from app.agents.main.runner.section_stream import (
    SectionStreamTracker,
    parse_closed_sections,
    should_stream_sections,
)


def test_should_stream_for_study_goals():
    assert should_stream_sections("Create a complete study sheet for Outbox")
    assert should_stream_sections("Teach me load balancers end to end")
    assert not should_stream_sections("List documents in this workspace")


def test_tracker_emits_only_closed_sections_mid_stream():
    events: list[tuple[str, dict]] = []

    def on_event(kind: str, payload: dict) -> None:
        events.append((kind, payload))

    tracker = SectionStreamTracker(
        on_event=on_event,
        run_id="r1",
        goal="Complete study sheet for Outbox",
    )
    # Incomplete: only section 1 open
    newly = tracker.feed(
        "## 1. Why Outbox?\n- Atomicity\n- Reliability\n"
    )
    assert newly == []
    assert not any(k == "section_draft" for k, _ in events)

    # Section 1 closed when 2 starts
    newly = tracker.feed(
        "## 1. Why Outbox?\n- Atomicity\n- Reliability\n\n"
        "## 2. High Level Flow\n1. Write DB\n2. Outbox\n"
    )
    assert len(newly) == 1
    assert newly[0]["index"] == 1
    assert newly[0]["title"] == "Why Outbox?"
    drafts = [p for k, p in events if k == "section_draft"]
    assert len(drafts) == 1
    assert drafts[0]["index"] == 1

    # Finish flushes section 2
    newly = tracker.finish(
        "## 1. Why Outbox?\n- Atomicity\n\n"
        "## 2. High Level Flow\n1. Write DB\n2. Outbox\n"
    )
    assert any(s["index"] == 2 for s in newly)
    assert len(tracker.sections) == 2
    assert any(k == "section_stream_complete" for k, _ in events)


def test_parse_closed_sections_full_answer():
    text = """
## 1. Why
- Point A

## 2. Flow
A → B → C

## 3. Best practices
- Index status
"""
    secs = parse_closed_sections(text)
    assert len(secs) == 3
    assert secs[0]["title"] == "Why"
    assert secs[1]["bullets"] == [] or "→" in secs[1]["body"]


def test_as_structured_sections_shape():
    tracker = SectionStreamTracker(goal="study sheet for X")
    tracker.finish(
        "## 1. Intro\nHello world body.\n\n## 2. Next\n- bullet one\n- bullet two\n"
    )
    structured = tracker.as_structured_sections()
    assert len(structured) == 2
    assert structured[0]["heading"].startswith("1.")
    assert structured[1]["bullets"]
