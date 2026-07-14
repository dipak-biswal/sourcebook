import uuid

from app.agents.execution_trace import build_execution_trace, emit_execution_trace
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
    assert turn["label"] == "Resume · turn 1"
    assert trace["workspace_name"] == "Resume"


def test_agent_turn_label_falls_back_to_agent():
    run = _run_with_steps("Hello", [{"type": "final", "output": "Hi"}])
    trace = build_execution_trace(run)
    turn = next(p for p in trace["phases"] if p["type"] == "agent_turn")
    assert turn["label"] == "Agent · turn 1"
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


def test_presentation_children_include_agent_turn_style_steps():
    run = _run_with_steps(
        "Summarize",
        [
            {"type": "tool_call", "tool_name": "web_search", "input": {"query": "x"}},
            {"type": "tool_result", "tool_name": "web_search", "output": {"results": []}},
            {
                "type": "final",
                "input": {
                    "messages": [{"role": "human", "content": "go"}],
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
                "output": "answer",
            },
            {
                "type": "presentation",
                "tool_name": "generative_ui",
                "input": {
                    "model": "gpt-4o-mini",
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                    "llm_output": '{"title":"Summary"}',
                    "agent_evidence": {
                        "document_hits": [
                            {"filename": "Resume.pdf", "snippet": "PM experience"}
                        ],
                        "web_hits": [],
                    },
                },
                "output": {
                    "type": "generative_ui",
                    "title": "Summary",
                    "blocks": [{"type": "summary", "body": "text"}],
                },
            },
        ],
    )
    trace = build_execution_trace(run, workspace_name="Resume")
    pres = next(p for p in trace["phases"] if p["type"] == "presentation")
    children = pres["children"]
    labels = [c.get("label") for c in children]
    assert any("Resume · turn 1 ·" in str(l) for l in labels)
    assert any(c.get("label") == "Layout engine" for c in children)
    assert any(c.get("label") == "Generated UI" for c in children)
    assert any(c.get("tool_name") == "search_documents" for c in children)


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