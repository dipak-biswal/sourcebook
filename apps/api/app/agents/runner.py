"""Agent tool loop with human-in-the-loop and resume-after-approve."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.agents.profiles import agent_system_prompt, get_profile
from app.agents.tools import build_tools
from app.config import settings
from app.models import AgentRun, AgentStep, Document, Workspace
from app.presentation.context import PresentationContext
from app.presentation.engine import build_presentation
from app.presentation.planner import should_offer_presentation
from app.usage import estimate_tokens, log_usage

WRITE_TOOLS = frozenset({"create_note"})
PRESENTATION_TOOL = "generative_ui"

# on_event(event_type, payload) — used for LangSmith-style live traces (SSE)
EventCallback = Callable[[str, dict[str, Any]], None] | None

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


def _hash_args(name: str, args: dict[str, Any]) -> str:
    """Deterministic hash of a (tool_name, args) pair for duplicate detection."""
    raw = json.dumps([name, args], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


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
        "agent_type": run.agent_type or "general",
        "presentation_spec": run.presentation_spec,
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


def _weak_final_answer(answer: str | None) -> bool:
    a = (answer or "").strip()
    if not a or a == "(no final answer)":
        return True
    if a.startswith("Stopped after max_steps"):
        return True
    return len(a) < 40


def _tool_context_for_synthesis(messages: list[BaseMessage]) -> str:
    """Flatten list/search tool results into text for a wrap-up LLM call."""
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(
                msg.content if isinstance(msg.content, str) else str(msg.content)
            )
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("snippet") and item.get("filename"):
                    fn = item.get("filename") or "document"
                    parts.append(f"[{fn}] {item['snippet']}")
                elif item.get("filename") and item.get("status"):
                    parts.append(
                        f"Document: {item['filename']} (status: {item['status']})"
                    )
        elif isinstance(data, dict):
            if data.get("error"):
                parts.append(f"Tool error: {data['error']}")
            elif data.get("results") and data.get("query"):
                parts.append(f"Web search: {data['query']}")
                for hit in data.get("results") or []:
                    if not isinstance(hit, dict):
                        continue
                    title = hit.get("title") or "result"
                    snippet = hit.get("snippet") or ""
                    parts.append(f"[web] {title}: {snippet}")
    return "\n".join(parts[:24])


def _synthesize_final_answer(
    db: Session,
    run: AgentRun,
    messages: list[BaseMessage],
) -> str | None:
    """One no-tools LLM turn when the agent stopped without a written answer."""
    context = _tool_context_for_synthesis(messages)
    goal = (run.goal or "").strip()
    if not goal:
        return None

    if not context.strip():
        docs = (
            db.query(Document.filename, Document.status)
            .filter(Document.workspace_id == run.workspace_id)
            .order_by(Document.created_at.desc())
            .limit(10)
            .all()
        )
        if docs:
            doc_lines = ", ".join(f"{n} ({s})" for n, s in docs)
            return (
                f"I found documents in this workspace ({doc_lines}) but could not "
                "retrieve searchable text yet. Ensure files are fully ingested "
                "(status: ready), then try again."
            )
        return (
            "No documents are available in this workspace yet. Upload your resume "
            "or other files under Documents and wait until status is ready."
        )

    prompt = (
        "The workspace agent gathered tool results but did not produce a final "
        "written answer. Using ONLY the evidence below, answer the substantive "
        "question in the user's goal.\n\n"
        f"GOAL:\n{goal}\n\n"
        f"TOOL RESULTS:\n{context[:12000]}\n\n"
        "Write a clear markdown answer (bullets/sections OK) about the document content. "
        "Ignore any requests for visual summary, UI layouts, tables-as-widgets, "
        "progress bars, chips, or callouts — those are handled elsewhere. "
        "Do not mention tools, steps, or that you are synthesizing."
    )
    try:
        ai: AIMessage = _llm().invoke(  # type: ignore[assignment]
            [
                SystemMessage(
                    content=(
                        "You produce concise, accurate answers grounded in the "
                        "provided excerpts. No tools."
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )
        p, c, t = _tokens_from_ai_message(ai)
        _log_agent_usage(
            db,
            run,
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=t if t else (p + c),
        )
        text = _content_str(ai.content).strip()
        return text or None
    except Exception:
        return None


def _prefer_gen_ui_summary(messages: list[BaseMessage], fallback: str) -> str:
    if fallback and fallback not in ("(no final answer)",):
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


def _finalize_completed_run(
    db: Session,
    run: AgentRun,
    *,
    messages: list[BaseMessage],
    fallback_answer: str,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """Set final answer and attach auto-generated presentation when appropriate."""
    answer = _prefer_gen_ui_summary(messages, fallback_answer)
    if _weak_final_answer(answer):
        synthesized = _synthesize_final_answer(db, run, messages)
        if synthesized:
            answer = synthesized
            step_index += 1
            _append_step(
                db,
                run,
                step_index=step_index,
                type="synthesis",
                output=answer,
                on_event=on_event,
            )
    run.final_answer = answer
    run.status = "completed"
    return _offer_presentation_if_needed(
        db,
        run,
        step_index=step_index,
        on_event=on_event,
    )


def _is_presentation_pending(pending: dict[str, Any] | None) -> bool:
    if not pending:
        return False
    return (
        pending.get("name") == PRESENTATION_TOOL
        or pending.get("kind") == "presentation"
    )


def _offer_presentation_if_needed(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """Pause for human-in-the-loop before building generative UI."""
    if run.presentation_spec:
        return step_index
    if not should_offer_presentation(
        goal=run.goal or "",
        final_answer=run.final_answer,
        status=run.status,
    ):
        return step_index

    run.status = "waiting_approval"
    run.pending_tool = {
        "id": str(uuid.uuid4()),
        "name": PRESENTATION_TOOL,
        "kind": "presentation",
        "args": {
            "goal": run.goal,
            "answer_preview": (run.final_answer or "")[:240],
        },
    }
    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="approval",
        tool_name=PRESENTATION_TOOL,
        input=run.pending_tool.get("args"),
        output={
            "status": "waiting_approval",
            "kind": "presentation",
        },
        on_event=on_event,
    )
    _emit(
        on_event,
        "presentation_offer",
        run_id=str(run.id),
        status="waiting_approval",
        pending_tool=run.pending_tool,
        final_answer=run.final_answer,
    )
    return step_index


def _build_and_attach_presentation(
    db: Session,
    run: AgentRun,
    *,
    step_index: int,
    on_event: EventCallback = None,
) -> int:
    """Build generative UI spec and attach to the run (after user approves)."""
    if run.presentation_spec:
        return step_index

    ws = db.get(Workspace, run.workspace_id)
    filenames = [
        row[0]
        for row in db.query(Document.filename)
        .filter(Document.workspace_id == run.workspace_id)
        .order_by(Document.created_at.desc())
        .limit(20)
        .all()
    ]
    raw_tags = ws.tags if ws and isinstance(ws.tags, list) else []
    tags = [str(t).strip() for t in raw_tags if t and str(t).strip()]

    ctx = PresentationContext(
        workspace_id=run.workspace_id,
        user_id=run.user_id or uuid.UUID(int=0),
        goal=run.goal or "",
        final_answer=run.final_answer or "",
        workspace_name=ws.name if ws else "",
        workspace_description=(ws.description or "") if ws else "",
        workspace_tags=tags,
        document_filenames=filenames,
    )
    spec = build_presentation(db, ctx)
    if not isinstance(spec, dict) or spec.get("error"):
        return step_index

    run.presentation_spec = spec
    plain = spec.get("plain_summary")
    if plain and (not run.final_answer or run.final_answer == "(no final answer)"):
        run.final_answer = str(plain)

    step_index += 1
    _append_step(
        db,
        run,
        step_index=step_index,
        type="presentation",
        tool_name="generative_ui",
        output=spec,
        on_event=on_event,
    )
    _emit(on_event, "presentation", run_id=str(run.id), presentation_profile=spec.get("presentation_profile"))
    return step_index


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
    tools = build_tools(
        db,
        workspace_id=run.workspace_id,
        user_id=user_id,
        agent_type=run.agent_type,
    )
    tool_by_name = {t.name: t for t in tools}
    model = _llm().bind_tools(tools)

    step_index = (
        start_step_index
        if start_step_index is not None
        else max(0, _next_step_index(db, run.id) - 1)
    )
    seen_calls: set[str] = set()

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

            # Duplicate detection — check BEFORE appending ai so we don't
            # orphan tool_calls without ToolMessage responses.
            if ai.tool_calls:
                warn_about_loop = False
                for tc in ai.tool_calls:
                    h = _hash_args(tc.get("name") or "", tc.get("args") or {})
                    if h in seen_calls:
                        warn_about_loop = True
                    seen_calls.add(h)

                tool_result_count = sum(
                    1 for m in messages if isinstance(m, ToolMessage)
                )
                # Never abort before at least one tool round — avoids false positives
                # from duplicate hashes across runs/threads or twin calls in one turn.
                if warn_about_loop and tool_result_count > 0:
                    _emit(
                        on_event,
                        "loop_warning",
                        run_id=str(run.id),
                        message="Agent is repeating the same tool call — breaking loop",
                    )
                    # Don't append ai (would orphan tool_calls), don't re-invoke LLM.
                    # Just exit — repeated calls waste tokens.
                    run.status = "completed"
                    run.token_usage = total_tokens_acc or None
                    run.pending_tool = None
                    step_index = _finalize_completed_run(
                        db,
                        run,
                        messages=messages,
                        fallback_answer=_content_str(ai.content) or "(no final answer)",
                        step_index=step_index,
                        on_event=on_event,
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

            messages.append(ai)

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
                run.token_usage = total_tokens_acc or None
                run.pending_tool = None
                step_index = _finalize_completed_run(
                    db,
                    run,
                    messages=messages,
                    fallback_answer=content or "(no final answer)",
                    step_index=step_index,
                    on_event=on_event,
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

            write_calls = [
                tc for tc in ai.tool_calls if tc.get("name") in WRITE_TOOLS
            ]
            if write_calls:
                tc = write_calls[0]
                # Execute non-write tools from the same turn in parallel first
                read_before_write = [
                    rtc for rtc in ai.tool_calls if rtc.get("name") not in WRITE_TOOLS
                ]
                if read_before_write:
                    _emit(
                        on_event,
                        "parallel_group",
                        run_id=str(run.id),
                        tool_names=[rtc.get("name") for rtc in read_before_write],
                        count=len(read_before_write),
                    )
                    for rtc in read_before_write:
                        _emit(
                            on_event,
                            "tool_start",
                            run_id=str(run.id),
                            tool_name=rtc.get("name"),
                            tool_args=rtc.get("args"),
                            call_id=rtc.get("id"),
                        )

                    def _run_read(tc: dict) -> dict[str, Any]:
                        name = tc.get("name") or ""
                        args = tc.get("args") or {}
                        call_id = tc.get("id") or str(uuid.uuid4())
                        tool = tool_by_name.get(name)
                        t0 = time.perf_counter()
                        try:
                            result: Any = (
                                tool.invoke(args) if tool else {"error": f"Unknown tool: {name}"}
                            )
                        except Exception as e:
                            result = {"error": str(e)}
                        ms = (time.perf_counter() - t0) * 1000
                        return {"call_id": call_id, "name": name, "args": args, "result": result, "ms": ms}

                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        read_results = list(pool.map(_run_read, read_before_write))

                    for rr in read_results:
                        step_index += 1
                        _append_step(
                            db,
                            run,
                            step_index=step_index,
                            type="tool_result",
                            tool_name=rr["name"],
                            input=rr["args"],
                            output=rr["result"],
                            on_event=on_event,
                            duration_ms=round(rr["ms"], 1),
                        )
                        messages.append(
                            ToolMessage(
                                content=json.dumps(rr["result"], default=str),
                                tool_call_id=rr["call_id"],
                                name=rr["name"],
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

            # Emit tool_start events for every tool call in this turn
            for tc in ai.tool_calls:
                _emit(
                    on_event,
                    "tool_start",
                    run_id=str(run.id),
                    tool_name=tc.get("name"),
                    tool_args=tc.get("args"),
                    call_id=tc.get("id"),
                )

            # Execute read tools in parallel
            read_calls = [
                tc for tc in ai.tool_calls if tc.get("name") not in WRITE_TOOLS
            ]

            if read_calls:
                _emit(
                    on_event,
                    "parallel_group",
                    run_id=str(run.id),
                    tool_names=[tc.get("name") for tc in read_calls],
                    count=len(read_calls),
                )

                def _run_one(tc: dict) -> dict[str, Any]:
                    name = tc.get("name") or ""
                    args = tc.get("args") or {}
                    call_id = tc.get("id") or str(uuid.uuid4())
                    tool = tool_by_name.get(name)
                    t0 = time.perf_counter()
                    if not tool:
                        result: Any = {"error": f"Unknown tool: {name}"}
                    else:
                        try:
                            result = tool.invoke(args)
                        except Exception as e:
                            result = {"error": str(e)}
                    ms = (time.perf_counter() - t0) * 1000
                    return {"call_id": call_id, "name": name, "args": args, "result": result, "ms": ms}

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(_run_one, read_calls))

                for r in results:
                    step_index += 1
                    _append_step(
                        db,
                        run,
                        step_index=step_index,
                        type="tool_result",
                        tool_name=r["name"],
                        input=r["args"],
                        output=r["result"],
                        on_event=on_event,
                        duration_ms=round(r["ms"], 1),
                    )
                    messages.append(
                        ToolMessage(
                            content=json.dumps(r["result"], default=str),
                            tool_call_id=r["call_id"],
                            name=r["name"],
                        )
                    )

        run.status = "completed"
        run.token_usage = total_tokens_acc or None
        run.pending_tool = None
        step_index = _finalize_completed_run(
            db,
            run,
            messages=messages,
            fallback_answer=(
                run.final_answer or "Stopped after max_steps without a final answer."
            ),
            step_index=step_index,
            on_event=on_event,
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
    agent_type: str = "general",
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

    profile = get_profile(agent_type)
    resolved_type = profile.agent_type
    cap_steps = max(1, min(max_steps, 12))

    run = AgentRun(
        workspace_id=workspace_id,
        user_id=user_id,
        goal=goal,
        agent_type=resolved_type,
        status="running",
        pending_tool=None,
    )
    db.add(run)
    db.flush()

    messages: list[BaseMessage] = [
        SystemMessage(content=agent_system_prompt(profile.system_prompt)),
        HumanMessage(content=goal),
    ]
    _emit(
        on_event,
        "run_start",
        run_id=str(run.id),
        goal=goal,
        workspace_id=str(workspace_id),
        agent_type=resolved_type,
        status="running",
    )
    return _run_tool_loop(
        db,
        run,
        messages=messages,
        max_steps=cap_steps,
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
        if _is_presentation_pending(pending):
            run.status = "completed"
            run.pending_tool = None
        else:
            run.status = "cancelled"
            run.pending_tool = None
            run.final_answer = f"Write action `{name}` was rejected by the user."
        db.commit()
        db.refresh(run)
        return run

    if _is_presentation_pending(pending):
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
        step_index = _build_and_attach_presentation(
            db,
            run,
            step_index=step_index,
            on_event=on_event,
        )
        run.status = "completed"
        run.pending_tool = None
        db.commit()
        db.refresh(run)
        _emit(
            on_event,
            "status",
            run_id=str(run.id),
            status=run.status,
            final_answer=run.final_answer,
            presentation_spec=run.presentation_spec,
        )
        return run

    if name not in WRITE_TOOLS:
        raise ValueError(f"Pending tool is not a write tool: {name}")

    tools = {
        t.name: t
        for t in build_tools(
            db,
            workspace_id=run.workspace_id,
            user_id=run.user_id or uuid.UUID(int=0),
            agent_type=run.agent_type,
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
        profile = get_profile(run.agent_type)
        messages = [
            SystemMessage(content=agent_system_prompt(profile.system_prompt)),
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
