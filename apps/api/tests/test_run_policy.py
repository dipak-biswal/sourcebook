"""Main-agent per-run tool policy (HITL evidence plan + date gating)."""

from app.agents.context.merge import CollectedContextSnapshot
from app.agents.main.run_policy import (
    apply_snapshot_to_tool_policy,
    apply_tool_policy_to_base_prompt,
    evidence_constraint_lines,
    format_run_tool_policy_block,
    goal_is_time_sensitive,
    run_requires_date_tool,
)
from app.agents.main.tool_policy import prepare_read_tool_calls
from app.agents.visual_summary.workspace.context import derive_workspace_context


def _packet(*, external_ok: bool = True):
    p = derive_workspace_context(
        name="WS",
        description="Study notes for systems design",
        tags=["learning"],
        document_rows=[("a.pdf", "ready")],
    )
    p.derived.tool_policy.external_context_ok = external_ok
    return p


def test_goal_time_sensitive():
    assert goal_is_time_sensitive("What is the latest market salary for SRE?")
    assert goal_is_time_sensitive("news today about Kubernetes")
    assert not goal_is_time_sensitive("Explain the CAP theorem from my notes")


def test_docs_only_disables_web():
    packet = _packet(external_ok=True)
    snap = CollectedContextSnapshot(document_plan="Workspace documents")
    summary = apply_snapshot_to_tool_policy(packet, snap)
    assert summary["evidence_plan"] == "docs"
    assert summary["allow_web_search"] is False
    assert summary["allow_fetch_url"] is False
    assert packet.derived.tool_policy.external_context_ok is False


def test_docs_only_with_urls_fetch_not_search():
    packet = _packet(external_ok=True)
    snap = CollectedContextSnapshot(
        document_plan="upload",
        urls=["https://example.com/spec"],
    )
    summary = apply_snapshot_to_tool_policy(packet, snap)
    assert summary["evidence_plan"] == "docs"
    assert summary["allow_web_search"] is False
    assert summary["allow_fetch_url"] is True
    assert packet.derived.tool_policy.external_context_ok is True
    assert packet.derived.tool_policy.max_web_search == 0


def test_web_plan_enables_web():
    packet = _packet(external_ok=False)
    snap = CollectedContextSnapshot(document_plan="web")
    summary = apply_snapshot_to_tool_policy(packet, snap)
    assert summary["allow_web_search"] is True
    assert summary["allow_fetch_url"] is True
    assert packet.derived.tool_policy.external_context_ok is True


def test_require_date_when_web_or_time_sensitive():
    assert run_requires_date_tool(allow_web=True, goal="Explain CAP") is True
    assert (
        run_requires_date_tool(
            allow_web=False, goal="Explain CAP theorem from my notes"
        )
        is False
    )
    assert (
        run_requires_date_tool(
            allow_web=False, goal="What is the current best practice in 2026?"
        )
        is True
    )
    assert (
        run_requires_date_tool(
            allow_web=False, goal="Summarize my notes", allow_fetch_url=True
        )
        is True
    )


def test_prepare_read_does_not_force_date_when_optional():
    calls = [
        {"name": "search_documents", "args": {"query": "x"}, "id": "1"},
    ]
    msgs, out_calls, date_first = prepare_read_tool_calls(
        calls,
        messages=[],
        is_main_agent=True,
        require_date=False,
    )
    assert date_first is False
    assert out_calls == calls
    assert msgs == []


def test_base_prompt_softens_date_and_web():
    from app.agents.main.profiles import GENERAL_SYSTEM_PROMPT

    soft = apply_tool_policy_to_base_prompt(
        GENERAL_SYSTEM_PROMPT, require_date=False, allow_web=False
    )
    assert "MUST be get_current_date" not in soft
    assert "optional this run" in soft
    assert "web_search, fetch_url" not in soft or "web tools are OFF" in soft


def test_policy_block_docs_fetch_only():
    block = format_run_tool_policy_block(
        allow_web=False,
        require_date=True,
        evidence_plan="docs",
        ready_doc_count=2,
        allow_fetch_url=True,
    )
    assert "web_search: OFF" in block
    assert "fetch_url: ALLOWED" in block
    assert "WORKSPACE DOCUMENTS" in block


def test_evidence_constraint_lines_docs_only():
    lines = evidence_constraint_lines(
        evidence_plan="docs", allow_web=False, allow_fetch_url=False
    )
    assert any("documents only" in ln for ln in lines)
