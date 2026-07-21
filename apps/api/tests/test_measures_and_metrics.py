"""Structured measures with numeric grounding (#8) and pipeline metrics (#12)."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.visual_summary.blocks.gen_ui import GenUIBlock, _normalize_block_dict, parse_measure_item
from app.visual_summary.tools import build_visual_tools
from app.models import UsageEvent
from app.visual_summary.context import PresentationContext
from app.visual_summary.render.engine import (
    _attach_measures,
    _ground_metric_numbers,
    _normalize_qualitative_progress,
    build_presentation,
)
from app.visual_summary.handoff.evidence import AgentEvidenceBundle, DocumentEvidenceHit
from app.routers.usage import summarize_visual_pipeline


# --- parse_measure_item ---


def test_parse_measure_numeric_with_unit():
    m = parse_measure_item("Latency | 200 ms")
    assert m is not None
    assert (m.label, m.value, m.numeric, m.unit) == ("Latency", "200 ms", 200.0, "ms")


def test_parse_measure_percent():
    m = parse_measure_item("Coverage | 85%")
    assert m is not None
    assert m.numeric == 85.0
    assert m.unit == "%"


def test_parse_measure_qualitative_and_invalid():
    m = parse_measure_item("Onboarding | Gap")
    assert m is not None and m.numeric is None and m.value == "Gap"
    assert parse_measure_item("no pipe here") is None


def test_normalize_block_keeps_label_value_dicts():
    norm = _normalize_block_dict(
        {
            "type": "metrics",
            "title": "KPIs",
            "data": [
                {"label": "Latency", "value": 200, "unit": "ms"},
                {"label": "Coverage", "value": "85%"},
            ],
        }
    )
    assert norm is not None
    assert norm["items"] == ["Latency | 200 ms", "Coverage | 85%"]


# --- numeric grounding ---


def test_metrics_rows_with_ungrounded_numbers_are_dropped():
    blocks = [
        GenUIBlock(
            type="metrics",
            items=["Latency | 200 ms", "Uptime | 99.99%", "Focus | High"],
        )
    ]
    corpus = "The latency budget is 200 ms for search. Focus stays high."
    out = _ground_metric_numbers(blocks, corpus=corpus)
    assert out[0].items == ["Latency | 200 ms", "Focus | High"]


def test_metrics_block_dropped_when_all_numbers_ungrounded():
    blocks = [GenUIBlock(type="metrics", items=["Revenue | $4.2M"])]
    out = _ground_metric_numbers(blocks, corpus="no numbers were stated")
    assert out == []


def test_metrics_comma_numbers_match():
    blocks = [GenUIBlock(type="metrics", items=["Users | 1,200"])]
    out = _ground_metric_numbers(blocks, corpus="grew to 1200 users this year")
    assert out and out[0].items == ["Users | 1,200"]


def test_progress_number_grounded_via_evidence_corpus():
    blocks = [GenUIBlock(type="progress", items=["Coverage | 85"])]
    answer = "Coverage improved a lot."
    corpus = answer + " Test coverage reached 85 percent per the CI report."
    out = _normalize_qualitative_progress(blocks, answer=answer, corpus=corpus)
    assert out[0].items == ["Coverage | 85"]


def test_attach_measures_on_measure_blocks_only():
    blocks = [
        GenUIBlock(type="metrics", items=["Latency | 200 ms"]),
        GenUIBlock(type="key_points", items=["Latency | 200 ms"]),
    ]
    out = _attach_measures(blocks)
    assert out[0].measures and out[0].measures[0].numeric == 200.0
    assert out[1].measures is None


def test_build_presentation_grounds_metrics_and_attaches_measures():
    class FakeDB:
        def commit(self):
            pass

    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize performance",
        final_answer="Latency is 200 ms for the search endpoint.",
        structured_content={
            "summary": "Latency is 200 ms.",
            "key_points": ["Latency 200 ms"],
            "faq": [],
            "sections": [],
            "metrics": ["Latency | 200 ms", "Uptime | 99.99%"],
        },
        layout_plan={
            "presentation_profile": "workspace_derived",
            "components": ["metrics"],
            "block_outline": [
                {"type": "metrics", "title": "KPIs", "source_hint": "metrics"},
            ],
        },
        agent_evidence=AgentEvidenceBundle(
            document_hits=[
                DocumentEvidenceHit(
                    filename="Perf.pdf",
                    snippet="Latency is 200 ms for the search endpoint.",
                    chunk_id="c1",
                    document_id="d1",
                )
            ]
        ),
    )
    spec, _ = build_presentation(FakeDB(), ctx)
    assert not spec.get("error"), spec
    metrics = next(b for b in spec["blocks"] if b["type"] == "metrics")
    assert metrics["items"] == ["Latency | 200 ms"]  # 99.99 not stated anywhere
    assert metrics["measures"][0]["numeric"] == 200.0


# --- #12: pipeline metrics ---


def test_render_logs_usage_row_even_for_code_assembly(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "visual_summary_llm_planner", False)
    db = MagicMock()
    ctx = PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize the workspace",
        final_answer="React and FastAPI are the core stack; RAG shipped.",
        structured_content={
            "summary": "React and FastAPI are the core stack; RAG shipped.",
            "key_points": ["Shipped RAG features", "TypeScript and Python"],
            "faq": [],
            "sections": [],
        },
        agent_evidence=AgentEvidenceBundle(),
    )
    by_name = {
        t.name: t
        for t in build_visual_tools(
            db, workspace_id=ctx.workspace_id, user_id=ctx.user_id, ctx=ctx
        )
    }
    by_name["plan_layout"].invoke({"notes": ""})
    res = by_name["render_ui"].invoke({"layout_plan_json": "{}"})
    assert res["status"] == "rendered"

    logged_kinds = [
        a.args[0].kind
        for a in db.add.call_args_list
        if a.args and isinstance(a.args[0], UsageEvent)
    ]
    assert "visual_summary_plan_outcome" in logged_kinds
    assert "visual_summary_render" in logged_kinds

    render_row = next(
        a.args[0]
        for a in db.add.call_args_list
        if a.args
        and isinstance(a.args[0], UsageEvent)
        and a.args[0].kind == "visual_summary_render"
    )
    assert render_row.meta["render_fallback_used"] is False
    assert render_row.meta["block_count"] >= 1
    assert render_row.meta["plan_prevalidated"] is True


def test_summarize_visual_pipeline_rates():
    def row(kind, meta=None, tokens=0):
        return SimpleNamespace(kind=kind, meta=meta or {}, total_tokens=tokens)

    rows = [
        row(
            "visual_summary_plan_outcome",
            {"validation_status": "passed", "replan_attempted": False, "planner_source": "llm"},
        ),
        row(
            "visual_summary_plan_outcome",
            {"validation_status": "failed", "replan_attempted": True, "planner_source": "skeleton"},
        ),
        row(
            "visual_summary_render",
            {"render_fallback_used": False, "block_count": 4, "dropped_blocks": 1},
        ),
        row(
            "visual_summary_render",
            {"render_fallback_used": True, "block_count": 2, "dropped_blocks": 0},
            tokens=900,
        ),
        row("visual_summary_plan", {}, tokens=500),
        row("chat", {"ignored": True}, tokens=999),
    ]
    s = summarize_visual_pipeline(rows)
    assert s.plan_count == 2
    assert s.render_count == 2
    assert s.validation_failed_rate == 0.5
    assert s.replan_rate == 0.5
    assert s.skeleton_fallback_rate == 0.5
    assert s.render_fallback_rate == 0.5
    assert s.avg_block_count == 3.0
    assert s.dropped_block_total == 1
    assert s.tokens_by_kind == {
        "visual_summary_plan_outcome": 0,
        "visual_summary_render": 900,
        "visual_summary_plan": 500,
    }
