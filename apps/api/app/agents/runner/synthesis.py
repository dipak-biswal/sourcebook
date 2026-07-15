"""Fallback final-answer synthesis when the agent stops without one."""

from __future__ import annotations

import json

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.orm import Session

from app.agents.runner.llm import _llm, _log_agent_usage, _tokens_for_turn
from app.agents.runner.messages import _content_str, _serialize_messages
from app.config import settings
from app.models import AgentRun, Document


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
            "No documents are available in this workspace yet. Upload files under "
            "Documents and wait until status is ready."
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
    synthesis_messages = [
        SystemMessage(
            content=(
                "You produce concise, accurate answers grounded in the "
                "provided excerpts. No tools."
            )
        ),
        HumanMessage(content=prompt),
    ]
    try:
        ai: AIMessage = _llm().invoke(synthesis_messages)  # type: ignore[assignment]
        p, c, t = _tokens_for_turn(synthesis_messages, ai)
        _log_agent_usage(
            db,
            run,
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=t if t else (p + c),
        )
        text = _content_str(ai.content).strip()
        if not text:
            return None
        run._synthesis_trace_input = {  # type: ignore[attr-defined]
            "messages": _serialize_messages(synthesis_messages),
            "model": settings.chat_model,
            "prompt_tokens": p,
            "completion_tokens": c,
            "total_tokens": t if t else (p + c),
        }
        return text
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
