import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.agents.tools import build_tools
from app.config import settings
from app.models import AgentRun, AgentStep
from app.usage import estimate_tokens, log_usage

WRITE_TOOLS = frozenset({"create_note"})


def _llm():
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=SecretStr(settings.openai_api_key),
        base_url=settings.openai_base_url,
        temperature=0.1,
    )


def _content_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _tokens_from_ai_message(ai: AIMessage) -> tuple[int, int, int]:
    """
    Return (prompt_tokens, completion_tokens, total_tokens) for one model turn.
    Prefer provider usage_metadata; fall back to rough char estimate.
    """
    meta = getattr(ai, "usage_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        prompt = int(meta.get("input_tokens") or meta.get("prompt_tokens") or 0)
        completion = int(
            meta.get("output_tokens") or meta.get("completion_tokens") or 0
        )
        total = int(meta.get("total_tokens") or (prompt + completion) or 0)
        if total > 0:
            return prompt, completion, total

    # response_metadata (OpenAI-style) sometimes used by older adapters
    resp = getattr(ai, "response_metadata", None) or {}
    usage = resp.get("token_usage") or resp.get("usage") or {}
    if isinstance(usage, dict) and usage:
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total = int(usage.get("total_tokens") or (prompt + completion) or 0)
        if total > 0:
            return prompt, completion, total

    # Fallback: content + tool call args (tool-only turns often have empty content)
    parts: list[str] = [_content_str(ai.content)]
    for tc in ai.tool_calls or []:
        parts.append(str(tc.get("name") or ""))
        parts.append(json.dumps(tc.get("args") or {}, default=str))
    est = estimate_tokens(*parts)
    return 0, 0, est


def _log_agent_usage(
    db: Session,
    run: AgentRun,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
        return
    log_usage(
        db,
        kind="agent_run",
        model=settings.chat_model,
        user_id=run.user_id,
        workspace_id=run.workspace_id,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
        meta={"run_id": str(run.id), "status": run.status},
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


def _next_step_index(db: Session, run_id: uuid.UUID) -> int:
    last = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id)
        .order_by(AgentStep.step_index.desc())
        .first()
    )
    return (last.step_index + 1) if last else 1


def run_agent(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    goal: str,
    max_steps: int = 5,
) -> AgentRun:
    """
    Tool loop with human approval for write tools.

    Read tools run immediately. If the model calls create_note, the run
    pauses at status=waiting_approval until approve_agent_run().
    """
    goal = goal.strip()
    if not goal:
        raise ValueError("goal is empty")

    run = AgentRun(
        workspace_id=workspace_id,
        user_id=user_id,
        goal=goal,
        status="running",
        pending_tool=None,
    )
    db.add(run)
    db.flush()

    tools = build_tools(db, workspace_id=workspace_id, user_id=user_id)
    tool_by_name = {t.name: t for t in tools}
    model = _llm().bind_tools(tools)

    system = SystemMessage(
        content=(
            "You are Sourcebook's workspace agent. "
            "Use tools to list/search documents, generate easy learning UIs, "
            "and create notes. Stay inside this workspace. Be concise.\n"
            "- For 'explain', 'summarize simply', 'teach me', 'overview', "
            "'key points', or 'make this easy to understand', call "
            "explain_for_learners with a clear topic (and optional focus).\n"
            "- If the user names a file, list_documents first if needed, then "
            "pass document_id or document_filename into explain_for_learners.\n"
            "- After explain_for_learners succeeds, give a short text answer "
            "and mention that a structured learning view is shown in the UI.\n"
            "- create_note requires human approval before it executes.\n"
            "When finished, answer clearly without more tool calls."
        )
    )

    messages: list = [system, HumanMessage(content=goal)]
    step_index = 0
    prompt_tokens_total = 0
    completion_tokens_total = 0
    total_tokens_acc = 0

    try:
        for _ in range(max(1, max_steps)):
            ai: AIMessage = model.invoke(messages)  # type: ignore[assignment]
            messages.append(ai)

            p, c, t = _tokens_from_ai_message(ai)
            prompt_tokens_total += p
            completion_tokens_total += c
            total_tokens_acc += t if t else (p + c)

            # Log model turn
            if ai.tool_calls:
                for tc in ai.tool_calls:
                    step_index += 1
                    _append_step(
                        db,
                        run,
                        step_index=step_index,
                        type="tool_call",
                        tool_name=tc.get("name"),
                        input=tc.get("args"),
                    )
            content = _content_str(ai.content)
            if content:
                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="thought" if ai.tool_calls else "final",
                    output=content,
                )

            # No tools → done
            if not ai.tool_calls:
                run.status = "completed"
                run.final_answer = content or "(no final answer)"
                # Prefer learning-view summary if the model left a thin final text
                if not content or content == "(no final answer)":
                    for msg in reversed(messages):
                        if isinstance(msg, ToolMessage):
                            try:
                                data = json.loads(
                                    msg.content
                                    if isinstance(msg.content, str)
                                    else str(msg.content)
                                )
                            except Exception:
                                continue
                            if (
                                isinstance(data, dict)
                                and data.get("type") == "generative_ui"
                                and data.get("plain_summary")
                            ):
                                run.final_answer = str(data["plain_summary"])
                                break
                run.token_usage = total_tokens_acc or None
                run.pending_tool = None
                _log_agent_usage(
                    db,
                    run,
                    prompt_tokens=prompt_tokens_total,
                    completion_tokens=completion_tokens_total,
                    total_tokens=total_tokens_acc,
                )
                db.commit()
                db.refresh(run)
                return run

            # Write tool → pause for approval (first write only this turn)
            write_calls = [
                tc for tc in ai.tool_calls if tc.get("name") in WRITE_TOOLS
            ]
            if write_calls:
                tc = write_calls[0]
                run.status = "waiting_approval"
                run.pending_tool = {
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                }
                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="approval",
                    tool_name=tc.get("name"),
                    input=tc.get("args") or {},
                    output={"status": "waiting_approval"},
                )
                run.token_usage = total_tokens_acc or None
                run.final_answer = (
                    "Waiting for your approval to run "
                    f"`{tc.get('name')}` with args: {json.dumps(tc.get('args') or {})}"
                )
                _log_agent_usage(
                    db,
                    run,
                    prompt_tokens=prompt_tokens_total,
                    completion_tokens=completion_tokens_total,
                    total_tokens=total_tokens_acc,
                )
                db.commit()
                db.refresh(run)
                return run

            # Execute read tools only
            for tc in ai.tool_calls:
                name = tc.get("name") or ""
                args = tc.get("args") or {}
                call_id = tc.get("id") or str(uuid.uuid4())
                tool = tool_by_name.get(name)
                if not tool:
                    result: Any = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        result = tool.invoke(args)
                    except Exception as e:
                        result = {"error": str(e)}

                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="tool_result",
                    tool_name=name,
                    input=args,
                    output=result,
                )
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, default=str),
                        tool_call_id=call_id,
                        name=name,
                    )
                )

        # Hit max_steps without natural finish
        run.status = "completed"
        run.final_answer = (
            run.final_answer
            or "Stopped after max_steps without a final answer."
        )
        run.token_usage = total_tokens_acc or None
        _log_agent_usage(
            db,
            run,
            prompt_tokens=prompt_tokens_total,
            completion_tokens=completion_tokens_total,
            total_tokens=total_tokens_acc,
        )
        db.commit()
        db.refresh(run)
        return run

    except Exception as e:
        run.status = "failed"
        run.error = str(e)
        if total_tokens_acc:
            run.token_usage = total_tokens_acc
            _log_agent_usage(
                db,
                run,
                prompt_tokens=prompt_tokens_total,
                completion_tokens=completion_tokens_total,
                total_tokens=total_tokens_acc,
            )
        db.commit()
        db.refresh(run)
        raise


def approve_agent_run(
    db: Session,
    run: AgentRun,
    *,
    approve: bool,
) -> AgentRun:
    """Approve or reject a pending write tool on an agent run."""
    if run.status != "waiting_approval" or not run.pending_tool:
        raise ValueError("Run is not waiting for approval")

    pending = run.pending_tool
    name = pending.get("name")
    args = pending.get("args") or {}
    step_index = _next_step_index(db, run.id)

    if not approve:
        _append_step(
            db,
            run,
            step_index=step_index,
            type="approval",
            tool_name=name,
            input=args,
            output={"status": "rejected"},
        )
        run.status = "cancelled"
        run.pending_tool = None
        run.final_answer = f"Write action `{name}` was rejected by the user."
        db.commit()
        db.refresh(run)
        return run

    if name not in WRITE_TOOLS:
        raise ValueError(f"Pending tool is not a write tool: {name}")

    tools = {
        t.name: t
        for t in build_tools(
            db,
            workspace_id=run.workspace_id,
            user_id=run.user_id or uuid.UUID(int=0),
        )
    }
    tool = tools.get(name)
    if not tool:
        raise ValueError(f"Tool not found: {name}")

    try:
        result = tool.invoke(args)
    except Exception as e:
        _append_step(
            db,
            run,
            step_index=step_index,
            type="tool_result",
            tool_name=name,
            input=args,
            output={"error": str(e)},
        )
        run.status = "failed"
        run.error = str(e)
        run.pending_tool = None
        db.commit()
        db.refresh(run)
        return run

    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_result",
        tool_name=name,
        input=args,
        output=result,
    )
    run.status = "completed"
    run.pending_tool = None
    run.final_answer = f"Approved and executed `{name}`.\n\nResult: {json.dumps(result, default=str)}"
    db.commit()
    db.refresh(run)
    return run
