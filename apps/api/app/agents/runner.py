import json
import uuid
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from sqlalchemy.orm import Session

from app.agents.tools import build_tools
from app.config import settings
from app.models import AgentRun, AgentStep
from pydantic import SecretStr


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _llm():
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=SecretStr(settings.openai_api_key),
        base_url=settings.openai_base_url,
        temperature=0.1,
    )


def _append_step(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    type: str,
    tool_name: str | None = None,
    input: Any = None,
    output: Any = None,
) -> None:
    db.add(
        AgentStep(
            run_id=run.id,
            step_index=step_index,
            type=type,
            tool_name=tool_name,
            input=input,
            output=output,
        )
    )
    db.flush()


def run_agent(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    goal: str,
    max_steps: int = 5,
) -> AgentRun:
    goal = goal.strip()
    if not goal:
        raise ValueError("goal is empty")

    run = AgentRun(
        workspace_id=workspace_id, user_id=user_id, goal=goal, status="running"
    )
    db.add(run)
    db.flush()

    tools = build_tools(db, workspace_id=workspace_id, user_id=user_id)

    model = _llm().bind_tools(tools)

    system = SystemMessage(
        content=(
            "You are Sourcebook's workspace agent. "
            "Use tools to list/search docuemnts and create notes. "
            "Stay inside this workspace. Be concise. "
            "When done. answer clearly without more tool calls."
        )
    )

    def agent_node(state: AgentState) -> dict:
        response = model.invoke([system, *state["messages"]])
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]

        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    # Node names must match exactly: "agent" / "tools" (not "agents" / "tool")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")

    app = graph.compile()

    step_index = 0
    token_approx = 0
    state: AgentState = {"messages": [HumanMessage(content=goal)]}

    try:
        result = app.invoke(state, config={"recursion_limit": max(4, max_steps * 2)})
        messages = result["messages"]

        for msg in messages:
            if isinstance(msg, HumanMessage):
                continue
            if isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        step_index += 1
                        _append_step(
                            db,
                            run,
                            step_index=step_index,
                            type="tool_call",
                            tool_name=tc.get("name"),
                            input=tc.get("args"),
                        )
                content = msg.content
                if content:
                    step_index += 1
                    _append_step(
                        db,
                        run,
                        step_index=step_index,
                        type="thought" if msg.tool_calls else "final",
                        input=None,
                        output=content if isinstance(content, str) else str(content),
                    )
                    if isinstance(content, str):
                        token_approx += max(1, len(content) // 4)

            elif isinstance(msg, ToolMessage):
                step_index += 1
                out: Any
                try:
                    out = (
                        json.loads(msg.content)
                        if isinstance(msg.content, str)
                        else msg.content
                    )
                except Exception:
                    out = msg.content
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="tool_result",
                    tool_name=getattr(msg, "name", None),
                    output=out,
                )

        final = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                final = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                break
        if not final:
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content:
                    final = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    break

        run.status = "completed"
        run.final_answer = final or "(no final answer)"
        run.token_usage = token_approx or None
        db.commit()
        db.refresh(run)
        return run
    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        db.commit()
        db.refresh(run)
        raise
