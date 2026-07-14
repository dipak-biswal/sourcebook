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