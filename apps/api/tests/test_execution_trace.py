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
    tool_labels = [
        c.get("label")
        for vt in visual_turns
        for c in vt.get("children") or []
        if c.get("type") == "tool"
    ]
    assert "Plan layout" in tool_labels
    assert "Render UI" in tool_labels
    plan_tool = next(
        c
        for vt in visual_turns
        for c in vt.get("children") or []
        if c.get("type") == "tool" and c.get("tool_name") == "plan_layout"
    )
    planner = next(
        child for child in plan_tool.get("children") or [] if child.get("type") == "llm_response"
    )
    assert planner["label"] == "Layout planner LLM"
    assert planner.get("llm_role") == "embedded_planner"
    assert "prompt" not in (plan_tool.get("output") or {})
    assert plan_tool.get("has_embedded_llm") is True
    assert planner["prompt_tokens"] == 180
    assert planner["completion_tokens"] == 42
    assert planner["total_tokens"] == 222
    child_types = [c.get("type") for c in visual_turns[0].get("children") or []]
    assert child_types[0] == "handoff"
    handoff = visual_turns[0]["children"][0]
    assert handoff["input"]["goal"] == "Summarize resume with visual summary"
    assert handoff["input"]["structured_content"]["key_points_count"] == 2
    assert plan_tool["output"]["layout_plan"]["components"] == ["table", "progress"]
    assert "prompt" not in plan_tool["output"]
    assert plan_tool["output"]["structured_summary"]["summary"].startswith("Strong React")
    render_tool = next(
        c
        for c in visual_turns[0]["children"]
        if c.get("type") == "tool" and c.get("tool_name") == "render_ui"
    )
    assert render_tool["output"]["ui_preview"]["title"] == "Summary"
    assert render_tool["output"]["ui_preview"]["block_types"] == ["summary", "key_points"]
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
    assert labels.count("Orchestrator · Decision") == 2
    assert labels.index("Orchestrator · Decision") < labels.index("Plan layout")
    second_decision = labels.index("Orchestrator · Decision", 1)
    assert second_decision < labels.index("Render UI")
    assert labels[-1] == "Orchestrator · Response"


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