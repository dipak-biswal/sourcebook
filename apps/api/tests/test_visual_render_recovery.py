"""render_ui recovers when the model hands back malformed layout_plan_json."""

import uuid
from unittest.mock import MagicMock

from app.agents.visual_tools import build_visual_tools
from app.presentation.context import PresentationContext
from app.presentation.evidence import AgentEvidenceBundle


def _ctx() -> PresentationContext:
    return PresentationContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal="Summarize the workspace",
        final_answer="React and FastAPI are the core stack; RAG shipped.",
        structured_content={
            "summary": "React and FastAPI are the core stack; RAG shipped.",
            "key_points": ["Shipped RAG features", "TypeScript and Python"],
            "faq": [{"question": "What stack?", "answer": "React + FastAPI"}],
            "themes": ["rag", "stack"],
            "sections": [],
        },
        agent_evidence=AgentEvidenceBundle(),
    )


def _tools(ctx: PresentationContext) -> dict:
    tools = build_visual_tools(
        MagicMock(), workspace_id=ctx.workspace_id, user_id=ctx.user_id, ctx=ctx
    )
    return {t.name: t for t in tools}


def test_render_ui_recovers_from_malformed_json_via_cached_plan():
    ctx = _ctx()
    by_name = _tools(ctx)

    plan_res = by_name["plan_layout"].invoke({"notes": ""})
    assert plan_res["status"] in ("planned", "validation_failed")

    # Truncated / malformed JSON — exactly the failure seen in production.
    render_res = by_name["render_ui"].invoke({"layout_plan_json": '{"block_outline":[{'})
    assert render_res.get("error") is None, render_res
    assert render_res["status"] == "rendered"
    assert render_res["block_count"] >= 1


def test_render_ui_uses_cached_plan_when_arg_is_empty():
    ctx = _ctx()
    by_name = _tools(ctx)
    by_name["plan_layout"].invoke({"notes": ""})

    render_res = by_name["render_ui"].invoke({"layout_plan_json": "{}"})
    assert render_res.get("error") is None, render_res
    assert render_res["status"] == "rendered"


def test_render_ui_errors_without_plan_and_bad_json():
    ctx = _ctx()
    by_name = _tools(ctx)

    # No plan_layout call, malformed JSON → surfaces the parse error.
    render_res = by_name["render_ui"].invoke({"layout_plan_json": "{bad"})
    assert "Invalid layout_plan_json" in (render_res.get("error") or "")
