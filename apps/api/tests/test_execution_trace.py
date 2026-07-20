import uuid

from app.agents.execution_trace import (
    LiveTraceContext,
    build_execution_trace,
    emit_execution_trace,
)
from app.models import AgentRun, AgentStep


def _run_with_steps(goal: str, steps: list[dict]) -> AgentRun:
    run = AgentRun(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        goal=goal,
        status="completed",
    )
    run.steps = [
        AgentStep(
            id=uuid.uuid4(),
            run_id=run.id,
            step_index=i + 1,
            type=s["type"],
            tool_name=s.get("tool_name"),
            input=s.get("input"),
            output=s.get("output"),
        )
        for i, s in enumerate(steps)
    ]
    return run


def test_agent_turn_label_uses_workspace_name():
    run = _run_with_steps("Compare resume", [{"type": "final", "output": "Done."}])
    trace = build_execution_trace(run, workspace_name="Resume")
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    assert turn["label"] == "Resume Agent"
    assert trace["workspace_name"] == "Resume Agent"


def test_agent_turn_label_falls_back_to_agent():
    run = _run_with_steps("Hello", [{"type": "final", "output": "Hi"}])
    trace = build_execution_trace(run)
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    assert turn["label"] == "Agent"
    assert trace["workspace_name"] == "Agent"


def test_agent_turn_children_tools_before_llm():
    run = _run_with_steps(
        "Compare resume",
        [
            {"type": "tool_call", "tool_name": "web_search", "input": {"query": "pm jobs"}},
            {"type": "tool_result", "tool_name": "web_search", "output": {"results": []}},
            {"type": "final", "output": "Here is your answer."},
        ],
    )
    trace = build_execution_trace(run)
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    children = turn["children"]
    assert children[0]["type"] == "tool"
    assert children[1]["type"] == "llm_response"
    assert "answer" in children[1]["output"].lower()


def test_llm_response_includes_prompt_from_step_input():
    run = _run_with_steps(
        "Hello",
        [
            {
                "type": "final",
                "input": {
                    "messages": [
                        {"role": "system", "content": "You are helpful."},
                        {"role": "human", "content": "Hello"},
                    ]
                },
                "output": "Hi there.",
            },
        ],
    )
    trace = build_execution_trace(run)
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    llm = next(c for c in turn["children"] if c["type"] == "llm_response")
    assert llm["prompt"][1]["content"] == "Hello"
    assert llm["output"] == "Hi there."


def test_llm_response_includes_token_counts():
    run = _run_with_steps(
        "Hello",
        [
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "Hello"}],
                    "prompt_tokens": 120,
                    "completion_tokens": 45,
                    "total_tokens": 165,
                },
                "output": "Hi there.",
            },
        ],
    )
    trace = build_execution_trace(run)
    llm = next(
        c
        for p in trace["phases"]
        if p["type"] == "agent_turn"
        for c in p["children"]
        if c["type"] == "llm_response"
    )
    assert llm["prompt_tokens"] == 120
    assert llm["completion_tokens"] == 45


def test_agent_turn_shows_decision_before_tools_and_response():
    run = _run_with_steps(
        "Search",
        [
            {"type": "tool_call", "tool_name": "web_search", "input": {"query": "jobs"}},
            {
                "type": "thought",
                "input": {
                    "messages": [{"role": "human", "content": "goal"}],
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
                "output": "I'll search the web.",
            },
            {"type": "tool_result", "tool_name": "web_search", "output": {"results": []}},
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "goal"}],
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                },
                "output": "Here are results.",
            },
        ],
    )
    trace = build_execution_trace(run)
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    types = [c["type"] for c in turn["children"]]
    labels = [c.get("label") for c in turn["children"]]
    assert types == ["llm_response", "tool", "llm_response"]
    assert labels == ["Decision", "Web search", "Response"]


def test_token_counts_normalize_zero_split_from_total():
    run = _run_with_steps(
        "Hello",
        [
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "Hello world"}],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 55,
                },
                "output": "Hi there.",
            },
        ],
    )
    trace = build_execution_trace(run)
    llm = next(
        c
        for p in trace["phases"]
        if p["type"] == "agent_turn"
        for c in p["children"]
        if c["type"] == "llm_response"
    )
    assert llm["prompt_tokens"] > 0
    assert llm["completion_tokens"] > 0
    assert llm["total_tokens"] == llm["prompt_tokens"] + llm["completion_tokens"]


def test_llm_response_includes_model():
    run = _run_with_steps(
        "Hello",
        [
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "Hello"}],
                    "model": "gpt-4o-mini",
                },
                "output": "Hi",
            },
        ],
    )
    trace = build_execution_trace(run)
    llm = next(
        c
        for p in trace["phases"]
        if p["type"] == "agent_turn"
        for c in p["children"]
        if c["type"] == "llm_response"
    )
    assert llm["model"] == "gpt-4o-mini"


def test_execution_trace_token_usage_sums_all_llm_calls():
    run = _run_with_steps(
        "Summarize",
        [
            {
                "type": "thought",
                "input": {
                    "messages": [{"role": "human", "content": "go"}],
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
                "output": "search",
            },
            {"type": "tool_call", "tool_name": "web_search", "input": {"query": "x"}},
            {"type": "tool_result", "tool_name": "web_search", "output": {"results": []}},
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "go"}],
                    "prompt_tokens": 200,
                    "completion_tokens": 50,
                    "total_tokens": 250,
                },
                "output": "done",
            },
            {
                "type": "synthesis",
                "input": {
                    "messages": [{"role": "human", "content": "synth"}],
                    "prompt_tokens": 30,
                    "completion_tokens": 10,
                    "total_tokens": 40,
                },
                "output": "synthesized",
            },
            {
                "type": "presentation",
                "tool_name": "generative_ui",
                "input": {
                    "prompt_tokens": 500,
                    "completion_tokens": 150,
                    "total_tokens": 650,
                },
                "output": {"type": "generative_ui", "title": "Summary", "blocks": []},
            },
        ],
    )
    trace = build_execution_trace(run)
    usage = trace["token_usage"]
    assert usage["prompt_tokens"] == 830
    assert usage["completion_tokens"] == 230
    assert usage["total_tokens"] == 1060


def test_visual_summary_agent_turns_after_handoff():
    run = _run_with_steps(
        "Summarize resume with visual summary",
        [
            {
                "type": "final",
                "output": "Main agent answer with enough detail for layout.",
            },
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "approved"},
            },
            {
                "type": "agent_handoff",
                "output": {"status": "handoff", "agent": "Visual Summary Agent"},
            },
            {
                "type": "tool_call",
                "tool_name": "plan_layout",
                "input": {
                    "notes": "",
                    "goal": "Summarize resume with visual summary",
                    "structured_handoff": {
                        "summary": "Strong React and FastAPI experience.",
                        "key_points": ["Shipped RAG features", "Led API design"],
                        "faq": [{"question": "Top stack?", "answer": "React + FastAPI"}],
                        "sections": [],
                        "themes": ["Engineering"],
                    },
                },
            },
            {
                "type": "tool_result",
                "tool_name": "plan_layout",
                "input": {
                    "notes": "",
                    "model": "gpt-4o-mini",
                    "prompt": "Plan the resume dashboard",
                    "llm_output": '{"presentation_profile":"resume_dashboard"}',
                    "prompt_tokens": 180,
                    "completion_tokens": 42,
                    "total_tokens": 222,
                },
                "output": {
                    "status": "planned",
                    "layout_plan": {
                        "presentation_profile": "resume_dashboard",
                        "components": ["table", "progress"],
                        "block_outline": [
                            {"type": "table", "title": "Skills", "purpose": "skill matrix"}
                        ],
                        "rationale": "Table plus progress for resume scan.",
                    },
                    "structured_input": {
                        "structured_content": {
                            "summary": "Strong React and FastAPI experience.",
                            "key_points": ["Shipped RAG features"],
                            "faq": [],
                            "sections": [],
                        }
                    },
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 180,
                    "completion_tokens": 42,
                    "total_tokens": 222,
                },
            },
            {
                "type": "thought",
                "input": {
                    "messages": [{"role": "human", "content": "handoff"}],
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
                "output": "Plan looks good — rendering UI.",
            },
            {
                "type": "tool_call",
                "tool_name": "render_ui",
                "input": {"layout_plan_json": "{}"},
            },
            {
                "type": "tool_result",
                "tool_name": "render_ui",
                "output": {
                    "status": "rendered",
                    "llm_output": '{"title":"Summary","blocks":[]}',
                    "spec": {
                        "type": "generative_ui",
                        "title": "Summary",
                        "plain_summary": "Overview text",
                        "presentation_profile": "resume_dashboard",
                        "blocks": [
                            {"type": "summary", "body": "text"},
                            {"type": "key_points", "items": ["a", "b"]},
                        ],
                        "source_files": ["resume.pdf"],
                    },
                    "block_count": 2,
                },
            },
            {
                "type": "presentation",
                "tool_name": "generative_ui",
                "output": {
                    "type": "generative_ui",
                    "title": "Summary",
                    "blocks": [{"type": "summary", "body": "text"}],
                },
            },
        ],
    )
    trace = build_execution_trace(run, workspace_name="Resume")
    agent_turns = [p for p in trace["phases"] if p["type"] == "agent_turn"]
    assert agent_turns[0]["label"] == "Resume Agent"
    visual_turns = [p for p in agent_turns if p.get("agent_label") == "Visual Summary Agent"]
    assert len(visual_turns) >= 1
    visual = visual_turns[0]
    child_types = [c.get("type") for c in visual.get("children") or []]
    assert child_types == ["handoff", "visual_stage", "visual_stage", "final_answer"]
    handoff = visual["children"][0]
    assert handoff["label"] == "Hand off"
    assert handoff["output"] == "Main agent answer with enough detail for layout."
    assert "input" not in handoff
    plan_stage = visual["children"][1]
    assert plan_stage["label"] == "Plan layout"
    assert plan_stage["type"] == "visual_stage"
    plan_tool = next(c for c in plan_stage["children"] if c.get("label") == "Tool call")
    planner = next(c for c in plan_stage["children"] if c.get("label") == "LLM call")
    assert plan_tool["input"] == {"notes": ""}
    assert plan_tool["output"]["layout_plan"]["components"] == ["table", "progress"]
    assert "prompt" not in plan_tool["output"]
    assert planner["prompt_tokens"] == 180
    render_stage = visual["children"][2]
    assert render_stage["label"] == "Render UI"
    render_tool = next(c for c in render_stage["children"] if c.get("label") == "Tool call")
    assert render_tool["output"]["ui_preview"]["title"] == "Summary"
    final = visual["children"][3]
    assert final["label"] == "Final answer"
    assert final["output"] == '{"title":"Summary","blocks":[]}'
    pres = next(p for p in trace["phases"] if p["type"] == "presentation")
    assert pres.get("children") == []


def test_execution_trace_includes_plan_layout_tokens_in_total():
    run = _run_with_steps(
        "Summarize resume with visual summary",
        [
            {"type": "final", "output": "Main agent answer with enough detail for layout."},
            {
                "type": "thought",
                "input": {
                    "messages": [{"role": "human", "content": "handoff"}],
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60,
                },
                "output": "Planning layout",
            },
            {
                "type": "tool_result",
                "tool_name": "plan_layout",
                "input": {
                    "notes": "",
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 180,
                    "completion_tokens": 42,
                    "total_tokens": 222,
                },
                "output": {
                    "status": "planned",
                    "layout_plan": {"presentation_profile": "resume_dashboard"},
                    "prompt_tokens": 180,
                    "completion_tokens": 42,
                    "total_tokens": 222,
                },
            },
        ],
    )
    trace = build_execution_trace(run)
    usage = trace["token_usage"]
    assert usage["prompt_tokens"] == 230
    assert usage["completion_tokens"] == 52
    assert usage["total_tokens"] == 282


def test_hitl_before_presentation():
    run = _run_with_steps(
        "Summarize docs",
        [
            {"type": "final", "output": "Done"},
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "waiting_approval"},
            },
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "approved"},
            },
            {
                "type": "presentation",
                "tool_name": "generative_ui",
                "output": {"type": "generative_ui", "title": "Summary", "blocks": []},
            },
        ],
    )
    trace = build_execution_trace(run)
    types = [p["type"] for p in trace["phases"]]
    assert types.index("hitl") < types.index("presentation")


def test_visual_summary_interleaves_orchestrator_decisions_with_tools():
    run = _run_with_steps(
        "Explain with visual",
        [
            {"type": "final", "output": "Main answer."},
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "approved"},
            },
            {
                "type": "agent_handoff",
                "output": {"status": "handoff", "agent": "Visual Summary Agent"},
            },
            {"type": "tool_call", "tool_name": "plan_layout", "input": {"notes": ""}},
            {
                "type": "thought",
                "input": {"messages": [], "prompt_tokens": 5, "completion_tokens": 2},
                "output": "Planning layout.",
            },
            {
                "type": "tool_result",
                "tool_name": "plan_layout",
                "input": {"prompt": "hidden", "prompt_tokens": 10, "completion_tokens": 4},
                "output": {
                    "status": "planned",
                    "layout_plan": {"presentation_profile": "guide"},
                    "prompt": "hidden",
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                },
            },
            {"type": "tool_call", "tool_name": "render_ui", "input": {"layout_plan_json": "{}"}},
            {
                "type": "thought",
                "input": {"messages": [], "prompt_tokens": 6, "completion_tokens": 2},
                "output": "Rendering UI.",
            },
            {
                "type": "tool_result",
                "tool_name": "render_ui",
                "input": {"prompt": "hidden", "prompt_tokens": 20, "completion_tokens": 8},
                "output": {
                    "status": "rendered",
                    "spec": {"type": "generative_ui", "title": "T", "blocks": []},
                    "prompt": "hidden",
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                },
            },
            {"type": "final", "output": "Visual summary ready."},
        ],
    )
    trace = build_execution_trace(run)
    visual = next(
        p
        for p in trace["phases"]
        if p.get("type") == "agent_turn"
        and p.get("agent_label") == "Visual Summary Agent"
    )
    labels = [c.get("label") for c in visual.get("children") or []]
    assert "Hand off" in labels
    assert "Plan layout" in labels
    assert "Render UI" in labels
    assert labels.index("Plan layout") < labels.index("Render UI")
    plan_stage = next(c for c in visual["children"] if c.get("label") == "Plan layout")
    assert [c.get("label") for c in plan_stage["children"]] == ["Tool call", "LLM call"]


def test_visual_summary_handoff_uses_synthesis_and_run_final_answer():
    run = _run_with_steps(
        "Summarize with visual",
        [
            {
                "type": "synthesis",
                "output": "Synthesized main agent answer for the visual handoff.",
            },
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "approved"},
            },
            {
                "type": "agent_handoff",
                "input": {
                    "answer_preview": "Preview from handoff step.",
                },
                "output": {"status": "handoff", "agent": "Visual Summary Agent"},
            },
            {"type": "tool_call", "tool_name": "plan_layout", "input": {"notes": ""}},
            {
                "type": "tool_result",
                "tool_name": "plan_layout",
                "input": {
                    "prompt": "Plan prompt",
                    "llm_output": '{"presentation_profile":"guide"}',
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                },
                "output": {
                    "status": "planned",
                    "layout_plan": {
                        "presentation_profile": "guide",
                        "components": ["summary"],
                        "block_outline": [],
                    },
                },
            },
        ],
    )
    run.final_answer = "Synthesized main agent answer for the visual handoff."
    trace = build_execution_trace(run)
    visual = next(
        p
        for p in trace["phases"]
        if p.get("agent_label") == "Visual Summary Agent"
    )
    handoff = next(c for c in visual["children"] if c["type"] == "handoff")
    assert (
        handoff["output"]
        == "Synthesized main agent answer for the visual handoff."
    )
    plan_stage = next(c for c in visual["children"] if c["label"] == "Plan layout")
    plan_tool = next(c for c in plan_stage["children"] if c["label"] == "Tool call")
    assert plan_tool["output"]["layout_plan"]["presentation_profile"] == "guide"
    planner = next(c for c in plan_stage["children"] if c["label"] == "LLM call")
    assert planner["prompt_tokens"] == 12


def test_visual_summary_llm_does_not_reactivate_main_agent_turn():
    """After HITL approval, live LLM work belongs to Visual Summary Agent only."""
    run = _run_with_steps(
        "Explain documents",
        [
            {"type": "tool_call", "tool_name": "search_documents", "input": {}},
            {
                "type": "tool_result",
                "tool_name": "search_documents",
                "output": {"hits": []},
            },
            {"type": "final", "output": "Key points and FAQ."},
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "approved"},
            },
            {
                "type": "agent_handoff",
                "output": {"status": "handoff", "agent": "Visual Summary Agent"},
            },
        ],
    )
    run.status = "running"
    live = LiveTraceContext(
        llm_running=True,
        current_turn_id="vs-turn-1",
        visual_agent_active=True,
    )
    trace = build_execution_trace(run, live=live, workspace_name="Job Search")
    main_turns = [
        p
        for p in trace["phases"]
        if p["type"] == "agent_turn" and p.get("label") == "Job Search Agent"
    ]
    visual_turns = [
        p
        for p in trace["phases"]
        if p["type"] == "agent_turn"
        and p.get("agent_label") == "Visual Summary Agent"
    ]
    assert len(main_turns) == 1
    assert main_turns[0]["state"] == "done"
    assert len(visual_turns) == 1
    assert visual_turns[0]["state"] == "running"
    assert visual_turns[0]["llm_turn_id"] == "vs-turn-1"


def test_running_tools_only_mark_active_agent_turn():
    """Earlier completed turns must not spin when tools run on a later turn."""
    run = _run_with_steps(
        "Explain documents",
        [
            {"type": "tool_call", "tool_name": "list_documents", "input": {}},
            {
                "type": "tool_result",
                "tool_name": "list_documents",
                "output": {"documents": []},
            },
            {"type": "final", "output": "Listed docs."},
            {"type": "tool_call", "tool_name": "search_documents", "input": {"query": "RAG"}},
        ],
    )
    run.status = "running"
    live = LiveTraceContext(running_tool_names=["search_documents"])
    trace = build_execution_trace(run, live=live, workspace_name="Job Search")
    turns = [p for p in trace["phases"] if p["type"] == "agent_turn"]
    assert len(turns) == 2
    assert turns[0]["state"] == "done"
    assert turns[1]["state"] == "running"


def test_emit_execution_trace_uses_payload_dict():
    run = _run_with_steps("Hello", [{"type": "final", "output": "Hi"}])
    events: list[tuple[str, dict]] = []

    def on_event(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    emit_execution_trace(on_event, run)
    assert len(events) == 1
    assert events[0][0] == "trace"
    assert "execution_trace" in events[0][1]
    assert events[0][1]["execution_trace"]["goal"] == "Hello"

def _walk_nodes(nodes):
    for node in nodes:
        yield node
        yield from _walk_nodes(node.get("children") or [])


def test_tool_error_surfaces_in_trace_while_running():
    """A tool that returns an error dict marks its node errored, even mid-run."""
    run = _run_with_steps(
        "Build a visual summary",
        [
            {"type": "tool_call", "tool_name": "render_ui", "input": {"layout_plan_json": "{}"}},
            {
                "type": "tool_result",
                "tool_name": "render_ui",
                "output": {
                    "error": "Layout plan failed validation",
                    "validation_errors": ["block_outline is empty", "timeline needs dates"],
                },
            },
        ],
    )
    run.status = "running"
    trace = build_execution_trace(run, workspace_name="Docs")

    error_nodes = [n for n in _walk_nodes(trace["phases"]) if n.get("state") == "error"]
    assert len(error_nodes) == 1
    tool_node = error_nodes[0]
    assert tool_node["tool_name"] == "render_ui"
    assert "failed validation" in tool_node["error"]
    assert "block_outline is empty" in tool_node["error"]
    # Trace-level error + auto-focus even though the run is still "running"
    assert trace["error"] and "failed validation" in trace["error"]
    assert trace["active_phase_id"] == tool_node["id"]


def test_pending_hitl_wins_focus_over_soft_tool_error():
    """fetch_url 403 must not hide the approval UI when waiting on the user."""
    run = _run_with_steps(
        "Explain setTimeout",
        [
            {
                "type": "tool_call",
                "tool_name": "fetch_url",
                "input": {"url": "https://medium.com/example"},
            },
            {
                "type": "tool_result",
                "tool_name": "fetch_url",
                "output": {
                    "url": "https://medium.com/example",
                    "error": "HTTP 403 from https://medium.com/example",
                    "recoverable": True,
                },
            },
            {"type": "final", "output": "Answer from other sources."},
            {
                "type": "approval",
                "tool_name": "generative_ui",
                "output": {"status": "waiting_approval"},
            },
        ],
    )
    run.status = "waiting_approval"
    run.pending_tool = {
        "id": "pt1",
        "name": "generative_ui",
        "kind": "presentation",
        "args": {},
    }
    trace = build_execution_trace(run, workspace_name="Docs")

    # Tool node still errored in-tree, but banner is soft + focus is HITL.
    error_nodes = [n for n in _walk_nodes(trace["phases"]) if n.get("state") == "error"]
    assert error_nodes
    assert "403" in (error_nodes[0].get("error") or "")
    assert "error" not in trace or not trace.get("error")
    assert trace.get("soft_error") and "403" in trace["soft_error"]
    hitl = next(n for n in _walk_nodes(trace["phases"]) if n.get("type") == "hitl")
    assert hitl.get("pending") is True
    assert trace["active_phase_id"] == hitl["id"]


def test_visual_summary_render_error_surfaces_on_stage():
    """render_ui failing inside the Visual Summary Agent marks its stage errored."""
    run = _run_with_steps(
        "Summarize with a visual",
        [
            {"type": "final", "output": "Main agent answer with enough detail for layout."},
            {"type": "agent_handoff", "output": {"status": "handoff", "agent": "Visual Summary Agent"}},
            {"type": "tool_call", "tool_name": "render_ui", "input": {"layout_plan_json": "{}"}},
            {
                "type": "tool_result",
                "tool_name": "render_ui",
                "output": {"error": "Failed to generate presentation: boom"},
            },
        ],
    )
    run.status = "running"
    trace = build_execution_trace(run, workspace_name="Docs")

    error_nodes = [n for n in _walk_nodes(trace["phases"]) if n.get("state") == "error"]
    assert error_nodes, "expected an errored node in the visual summary trace"
    assert any("Failed to generate presentation" in (n.get("error") or "") for n in error_nodes)
    assert trace["error"] and "Failed to generate presentation" in trace["error"]
