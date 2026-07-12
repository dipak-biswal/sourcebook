"""Agent tool loop with human-in-the-loop and resume-after-approve."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.agents.tools import build_tools
from app.config import settings
from app.models import AgentRun, AgentStep
from app.usage import estimate_tokens, log_usage

WRITE_TOOLS = frozenset({"create_note"})

# on_event(event_type, payload) — used for LangSmith-style live traces (SSE)
EventCallback = Callable[[str, dict[str, Any]], None] | None

SYSTEM_PROMPT = (
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
    "- create_note requires human approval before it executes. "
    "After a write is approved and executed, continue helping if useful "
    "(confirm what was done, suggest next steps) without re-calling the same write unless asked.\n"
    "When finished, answer clearly without more tool calls."
)


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
    meta = getattr(ai, "usage_metadata", None) or {}
    if isinstance(meta, dict) and meta:
        prompt = int(meta.get("input_tokens") or meta.get("prompt_tokens") or 0)
        completion = int(
            meta.get("output_tokens") or meta.get("completion_tokens") or 0
        )
        total = int(meta.get("total_tokens") or (prompt + completion) or 0)
        if total > 0:
            return prompt, completion, total

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


def step_to_dict(step: AgentStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "step_index": step.step_index,
        "type": step.type,
        "tool_name": step.tool_name,
        "input": step.input,
        "output": step.output,
        "created_at": step.created_at.isoformat() if step.created_at else None,
    }


def run_to_public_dict(run: AgentRun) -> dict[str, Any]:
    steps = sorted(run.steps or [], key=lambda s: s.step_index)
    return {
        "id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "user_id": str(run.user_id) if run.user_id else None,
        "goal": run.goal,
        "status": run.status,
        "final_answer": run.final_answer,
        "error": run.error,
        "token_usage": run.token_usage,
        "pending_tool": run.pending_tool,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "steps": [step_to_dict(s) for s in steps],
    }


def _emit(on_event: EventCallback, event_type: str, **payload: Any) -> None:
    if on_event:
        on_event(event_type, payload)


def _append_step(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    type: str,
    tool_name: str | None = None,
    input: Any = None,
    output: Any = None,
    on_event: EventCallback = None,
    duration_ms: float | None = None,
) -> AgentStep:
    step = AgentStep(
        run_id=run.id,
        step_index=step_index,
        type=type,
        tool_name=tool_name,
        input=input,
        output=output,
    )
    db.add(step)
    db.flush()
    db.refresh(step)
    payload = step_to_dict(step)
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 1)
    _emit(on_event, "step", step=payload, run_id=str(run.id), status=run.status)
    return step


def _next_step_index(db: Session, run_id: uuid.UUID) -> int:
    last = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id)
        .order_by(AgentStep.step_index.desc())
        .first()
    )
    return (last.step_index + 1) if last else 1


def _serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": _content_str(m.content)})
        elif isinstance(m, HumanMessage):
            out.append({"role": "human", "content": _content_str(m.content)})
        elif isinstance(m, AIMessage):
            item: dict[str, Any] = {
                "role": "ai",
                "content": _content_str(m.content),
            }
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.get("id"),
                        "name": tc.get("name"),
                        "args": tc.get("args") or {},
                        "type": tc.get("type") or "tool_call",
                    }
                    for tc in m.tool_calls
                ]
            out.append(item)
        elif isinstance(m, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "content": _content_str(m.content),
                    "tool_call_id": m.tool_call_id,
                    "name": getattr(m, "name", None) or "",
                }
            )
    return out


def _deserialize_messages(raw: list[Any]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role == "system":
            messages.append(SystemMessage(content=str(item.get("content") or "")))
        elif role == "human":
            messages.append(HumanMessage(content=str(item.get("content") or "")))
        elif role == "ai":
            tool_calls = item.get("tool_calls") or []
            messages.append(
                AIMessage(
                    content=str(item.get("content") or ""),
                    tool_calls=tool_calls,
                )
            )
        elif role == "tool":
            messages.append(
                ToolMessage(
                    content=str(item.get("content") or ""),
                    tool_call_id=str(item.get("tool_call_id") or str(uuid.uuid4())),
                    name=str(item.get("name") or ""),
                )
            )
    return messages


def _prefer_gen_ui_summary(messages: list[BaseMessage], fallback: str) -> str:
    if fallback and fallback not in ("(no final answer)",):
        # Still upgrade empty-ish answers
        if len(fallback.strip()) > 20:
            return fallback
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
            except Exception:
                continue
            if (
                isinstance(data, dict)
                and data.get("type") == "generative_ui"
                and data.get("plain_summary")
            ):
                return str(data["plain_summary"])
    return fallback or "(no final answer)"


def _run_tool_loop(
    db: Session,
    run: AgentRun,
    *,
    messages: list[BaseMessage],
    max_steps: int,
    prompt_tokens_total: int = 0,
    completion_tokens_total: int = 0,
    total_tokens_acc: int = 0,
    start_step_index: int | None = None,
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Shared LLM ↔ tools loop.

    Pauses on first write tool with a checkpoint in pending_tool so approve can resume.
    """
    user_id = run.user_id or uuid.UUID(int=0)
    tools = build_tools(db, workspace_id=run.workspace_id, user_id=user_id)
    tool_by_name = {t.name: t for t in tools}
    model = _llm().bind_tools(tools)

    step_index = (
        start_step_index
        if start_step_index is not None
        else max(0, _next_step_index(db, run.id) - 1)
    )

    try:
        for _ in range(max(1, max_steps)):
            _emit(
                on_event,
                "llm_start",
                run_id=str(run.id),
                name="ChatOpenAI",
                status=run.status,
            )
            t0 = time.perf_counter()
            ai: AIMessage = model.invoke(messages)  # type: ignore[assignment]
            llm_ms = (time.perf_counter() - t0) * 1000
            messages.append(ai)

            p, c, t = _tokens_from_ai_message(ai)
            prompt_tokens_total += p
            completion_tokens_total += c
            total_tokens_acc += t if t else (p + c)
            _emit(
                on_event,
                "llm_end",
                run_id=str(run.id),
                name="ChatOpenAI",
                duration_ms=round(llm_ms, 1),
                prompt_tokens=p,
                completion_tokens=c,
                total_tokens=t if t else (p + c),
                has_tool_calls=bool(ai.tool_calls),
                token_usage_so_far=total_tokens_acc,
            )

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
                        on_event=on_event,
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
                    on_event=on_event,
                    duration_ms=llm_ms if not ai.tool_calls else None,
                )

            if not ai.tool_calls:
                run.status = "completed"
                run.final_answer = _prefer_gen_ui_summary(
                    messages, content or "(no final answer)"
                )
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
                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status=run.status,
                    token_usage=run.token_usage,
                    final_answer=run.final_answer,
                )
                return run

            write_calls = [
                tc for tc in ai.tool_calls if tc.get("name") in WRITE_TOOLS
            ]
            if write_calls:
                tc = write_calls[0]
                # Execute non-write tools from the same turn first (if any)
                for rtc in ai.tool_calls:
                    rname = rtc.get("name") or ""
                    if rname in WRITE_TOOLS:
                        continue
                    rargs = rtc.get("args") or {}
                    rid = rtc.get("id") or str(uuid.uuid4())
                    rtool = tool_by_name.get(rname)
                    try:
                        rresult: Any = (
                            rtool.invoke(rargs)
                            if rtool
                            else {"error": f"Unknown tool: {rname}"}
                        )
                    except Exception as e:
                        rresult = {"error": str(e)}
                    step_index += 1
                    _append_step(
                        db,
                        run,
                        step_index=step_index,
                        type="tool_result",
                        tool_name=rname,
                        input=rargs,
                        output=rresult,
                        on_event=on_event,
                    )
                    messages.append(
                        ToolMessage(
                            content=json.dumps(rresult, default=str),
                            tool_call_id=rid,
                            name=rname,
                        )
                    )

                run.status = "waiting_approval"
                run.pending_tool = {
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                    # Checkpoint for resume-after-approve
                    "checkpoint": {
                        "messages": _serialize_messages(messages),
                        "max_steps": max_steps,
                        "prompt_tokens": prompt_tokens_total,
                        "completion_tokens": completion_tokens_total,
                        "total_tokens": total_tokens_acc,
                    },
                }
                step_index += 1
                _append_step(
                    db,
                    run,
                    step_index=step_index,
                    type="approval",
                    tool_name=tc.get("name"),
                    input=tc.get("args") or {},
                    output={
                        "status": "waiting_approval",
                        "resumable": True,
                    },
                    on_event=on_event,
                )
                run.token_usage = total_tokens_acc or None
                run.final_answer = (
                    "Waiting for your approval to run "
                    f"`{tc.get('name')}` with args: {json.dumps(tc.get('args') or {})}. "
                    "After you approve, the agent will continue."
                )
                # Don't log completion usage yet — resume will log final
                db.commit()
                db.refresh(run)
                _emit(
                    on_event,
                    "status",
                    run_id=str(run.id),
                    status=run.status,
                    token_usage=run.token_usage,
                    pending_tool=run.pending_tool,
                    final_answer=run.final_answer,
                )
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
                    on_event=on_event,
                )
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, default=str),
                        tool_call_id=call_id,
                        name=name,
                    )
                )

        run.status = "completed"
        run.final_answer = (
            run.final_answer or "Stopped after max_steps without a final answer."
        )
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
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            token_usage=run.token_usage,
            final_answer=run.final_answer,
        )
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


def run_agent(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    goal: str,
    max_steps: int = 5,
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Tool loop with human approval for write tools.

    Read tools run immediately. Write tools pause at waiting_approval;
    approve_agent_run() executes the write and **resumes** the agent loop.
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

    messages: list[BaseMessage] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=goal),
    ]
    _emit(
        on_event,
        "run_start",
        run_id=str(run.id),
        goal=goal,
        workspace_id=str(workspace_id),
        status="running",
    )
    return _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=max(1, min(max_steps, 12)),
        start_step_index=0,
        on_event=on_event,
    )


def approve_agent_run(
    db: Session,
    run: AgentRun,
    *,
    approve: bool,
    on_event: EventCallback = None,
) -> AgentRun:
    """
    Approve or reject a pending write tool.

    On approve: execute the write, append the tool result, then **resume**
    the LLM tool loop so the agent can continue (confirm, next steps, etc.).
    On reject: mark cancelled (no resume).
    """
    if run.status != "waiting_approval" or not run.pending_tool:
        raise ValueError("Run is not waiting for approval")

    pending = dict(run.pending_tool)
    name = pending.get("name")
    args = pending.get("args") or {}
    call_id = pending.get("id") or str(uuid.uuid4())
    checkpoint = pending.get("checkpoint") if isinstance(pending.get("checkpoint"), dict) else {}
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
            on_event=on_event,
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
            on_event=on_event,
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
        type="approval",
        tool_name=name,
        input=args,
        output={"status": "approved"},
        on_event=on_event,
    )
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="tool_result",
        tool_name=name,
        input=args,
        output=result,
        on_event=on_event,
    )

    # Rebuild conversation and append successful write result
    messages = _deserialize_messages(checkpoint.get("messages") or [])
    if not messages:
        # Fallback if old runs lack checkpoint
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=run.goal or ""),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": call_id,
                        "name": name,
                        "args": args,
                        "type": "tool_call",
                    }
                ],
            ),
        ]
    messages.append(
        ToolMessage(
            content=json.dumps(result, default=str),
            tool_call_id=str(call_id),
            name=str(name),
        )
    )
    # Nudge: write is done; produce a final confirmation / next steps
    messages.append(
        HumanMessage(
            content=(
                f"[System] The user approved and `{name}` executed successfully. "
                f"Result: {json.dumps(result, default=str)}. "
                "Continue: briefly confirm what was done and any useful next steps. "
                "Do not call create_note again unless the user clearly asked for another note."
            )
        )
    )

    run.status = "running"
    run.pending_tool = None
    run.final_answer = None
    db.commit()

    remaining = int(checkpoint.get("max_steps") or 5)
    # Allow a few more steps after approval to finish cleanly
    resume_steps = max(2, min(remaining, 6))

    _emit(
        on_event,
        "status",
        run_id=str(run.id),
        status="running",
        message="resuming after approval",
    )
    return _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=resume_steps,
        prompt_tokens_total=int(checkpoint.get("prompt_tokens") or 0),
        completion_tokens_total=int(checkpoint.get("completion_tokens") or 0),
        total_tokens_acc=int(checkpoint.get("total_tokens") or 0),
        start_step_index=step_index,
        on_event=on_event,
    )
