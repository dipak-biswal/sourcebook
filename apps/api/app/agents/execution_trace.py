"""Build a UI-ready agent execution trace from run state and steps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import settings
from app.models import AgentRun, AgentStep
from app.usage import estimate_tokens

TraceState = Literal["pending", "running", "done"]

TOOL_LABELS: dict[str, str] = {
    "list_documents": "List documents",
    "search_documents": "Search workspace",
    "web_search": "Web search",
    "create_note": "Create note",
    "generative_ui": "Visual summary",
}

PRESENTATION_TOOL = "generative_ui"
COMPLETE_STATUSES = frozenset({"completed", "cancelled", "failed"})


def _tool_label(name: str | None) -> str:
    if not name:
        return "Tool"
    return TOOL_LABELS.get(name, name.replace("_", " "))


def _step_output_status(step: AgentStep | dict[str, Any]) -> str | None:
    output = step.output if isinstance(step, AgentStep) else step.get("output")
    if not output or not isinstance(output, dict):
        return None
    status = output.get("status")
    return str(status) if status is not None else None


def _normalize_token_counts(
    tokens: dict[str, int],
    *,
    step: AgentStep | None = None,
) -> dict[str, int]:
    p = int(tokens.get("prompt_tokens") or 0)
    c = int(tokens.get("completion_tokens") or 0)
    t = int(tokens.get("total_tokens") or 0)

    if step and p == 0 and c == 0 and t > 0:
        inp = step.input if isinstance(step.input, dict) else {}
        messages = inp.get("messages")
        prompt_est = (
            estimate_tokens(json.dumps(messages, default=str))
            if messages
            else 0
        )
        output_est = estimate_tokens(_step_text(step))
        if prompt_est + output_est > 0:
            p, c, t = prompt_est, output_est, prompt_est + output_est

    out: dict[str, int] = {}
    if p > 0:
        out["prompt_tokens"] = p
    if c > 0:
        out["completion_tokens"] = c
    if t > 0:
        out["total_tokens"] = t
    elif p > 0 or c > 0:
        out["total_tokens"] = p + c
    return out


def _tokens_from_step_input(step: AgentStep | None) -> dict[str, int]:
    if not step or not step.input or not isinstance(step.input, dict):
        return {}
    raw: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = step.input.get(key)
        if isinstance(value, int) and value >= 0:
            raw[key] = value
    return _normalize_token_counts(raw, step=step)


def _tokens_from_live(
    live: LiveTraceContext | None,
    turn_id: str | None,
) -> dict[str, int]:
    if not live or not turn_id:
        return {}
    raw = dict(live.tokens_by_turn.get(turn_id) or {})
    return _normalize_token_counts(raw)


def _apply_tokens(node: dict[str, Any], tokens: dict[str, int]) -> dict[str, Any]:
    if not tokens:
        return node
    merged = dict(node)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in tokens:
            merged[key] = tokens[key]
    return merged


def _model_from_step_input(step: AgentStep | None) -> str | None:
    if not step or not step.input or not isinstance(step.input, dict):
        return None
    model = step.input.get("model")
    return str(model).strip() if isinstance(model, str) and model.strip() else None


def _resolve_model(
    step: AgentStep | None,
    live: LiveTraceContext | None,
    turn_id: str | None,
) -> str:
    model = _model_from_step_input(step)
    if model:
        return model
    if live and turn_id:
        live_model = live.model_by_turn.get(turn_id)
        if live_model:
            return live_model
    return settings.chat_model


def _messages_from_step_input(step: AgentStep | None) -> list[dict[str, Any]] | None:
    if not step or not step.input or not isinstance(step.input, dict):
        return None
    messages = step.input.get("messages")
    if isinstance(messages, list):
        return messages
    return None


def _step_text(step: AgentStep | None) -> str:
    if not step or step.output is None:
        return ""
    if isinstance(step.output, str):
        return step.output
    return ""


def _is_generative_ui(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "generative_ui"
        and isinstance(value.get("title"), str)
    )


@dataclass
class LiveTraceContext:
    """In-memory stream state while a run is executing (not persisted)."""

    stream_by_turn: dict[str, str] = field(default_factory=dict)
    prompt_by_turn: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    tokens_by_turn: dict[str, dict[str, int]] = field(default_factory=dict)
    model_by_turn: dict[str, str] = field(default_factory=dict)
    current_turn_id: str | None = None
    llm_running: bool = False
    has_tool_calls: bool = False
    running_tool_names: list[str] = field(default_factory=list)
    approving: bool = False


def _step_dict(step: AgentStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "step_index": step.step_index,
        "type": step.type,
        "tool_name": step.tool_name,
        "input": step.input,
        "output": step.output,
    }


@dataclass
class _ToolAcc:
    id: str
    tool_name: str
    call_step: AgentStep | None = None
    result_step: AgentStep | None = None
    state: TraceState = "pending"

    def to_node(self) -> dict[str, Any]:
        node: dict[str, Any] = {
            "id": self.id,
            "type": "tool",
            "label": _tool_label(self.tool_name),
            "tool_name": self.tool_name,
            "state": self.state,
        }
        if self.call_step and self.call_step.input is not None:
            node["input"] = self.call_step.input
        elif self.result_step and self.result_step.input is not None:
            node["input"] = self.result_step.input
        if self.result_step and self.result_step.output is not None:
            node["output"] = self.result_step.output
        return node


@dataclass
class _TurnAcc:
    id: str
    turn: int
    tools: list[_ToolAcc] = field(default_factory=list)
    planning_step: AgentStep | None = None
    response_step: AgentStep | None = None
    state: TraceState = "done"
    llm_turn_id: str | None = None

    def prompt_for_output(self, live: LiveTraceContext | None) -> list[dict[str, Any]] | None:
        if self.response_step:
            stored = _messages_from_step_input(self.response_step)
            if stored:
                return stored
        if (
            live
            and self.llm_turn_id
            and live.llm_running
            and self.llm_turn_id == live.current_turn_id
        ):
            return live.prompt_by_turn.get(self.llm_turn_id)
        if self.planning_step:
            stored = _messages_from_step_input(self.planning_step)
            if stored:
                return stored
        if live and self.llm_turn_id:
            return live.prompt_by_turn.get(self.llm_turn_id)
        return None

    def response_content(self, live: LiveTraceContext | None) -> str:
        if self.response_step and self.response_step.type == "final":
            return _step_text(self.response_step)
        if self.tools:
            if self.response_step and self.response_step.type == "thought":
                pass
            elif live and self.llm_turn_id:
                return live.stream_by_turn.get(self.llm_turn_id, "")
            return ""
        if live and self.llm_turn_id:
            streamed = live.stream_by_turn.get(self.llm_turn_id, "")
            if streamed:
                return streamed
        return _step_text(self.response_step or self.planning_step)

    def _make_llm_node(
        self,
        *,
        suffix: str,
        label: str,
        step: AgentStep | None,
        live: LiveTraceContext | None,
        live_turn_id: str | None,
        state: TraceState,
        output: str,
        prompt: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        resolved_prompt = prompt
        if resolved_prompt is None and step:
            resolved_prompt = _messages_from_step_input(step)
        if resolved_prompt is None and live and live_turn_id:
            resolved_prompt = live.prompt_by_turn.get(live_turn_id)

        tokens = _tokens_from_step_input(step)
        if not tokens and live and live_turn_id:
            tokens = _tokens_from_live(live, live_turn_id)

        return _apply_tokens(
            {
                "id": f"{self.id}-llm-{suffix}",
                "type": "llm_response",
                "label": label,
                "state": state,
                "model": _resolve_model(step, live, live_turn_id),
                "prompt": resolved_prompt,
                "output": output,
            },
            tokens,
        )

    def _response_llm_state(self, live: LiveTraceContext | None) -> TraceState:
        if live and self.llm_turn_id == live.current_turn_id and live.llm_running:
            return "running"
        if self.response_step or self.state == "done":
            return "done"
        if live and self.llm_turn_id and live.stream_by_turn.get(self.llm_turn_id):
            return "running"
        return self.state

    def children(self, live: LiveTraceContext | None) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []

        if self.planning_step:
            nodes.append(
                self._make_llm_node(
                    suffix="decision",
                    label="Decision",
                    step=self.planning_step,
                    live=None,
                    live_turn_id=None,
                    state="done",
                    output=_step_text(self.planning_step),
                )
            )

        nodes.extend(t.to_node() for t in self.tools)

        has_response_step = self.response_step is not None
        live_response = bool(
            live
            and self.llm_turn_id
            and (
                (live.llm_running and self.llm_turn_id == live.current_turn_id)
                or live.stream_by_turn.get(self.llm_turn_id)
            )
        )
        show_response = has_response_step or live_response or (
            not self.planning_step and not self.tools
        )

        if show_response:
            response_output = self.response_content(live)
            nodes.append(
                self._make_llm_node(
                    suffix="response" if self.planning_step or self.tools else "llm",
                    label="Response" if (self.planning_step or self.tools) else "LLM output",
                    step=self.response_step,
                    live=live,
                    live_turn_id=self.llm_turn_id,
                    state=self._response_llm_state(live),
                    output=response_output,
                    prompt=self.prompt_for_output(live)
                    if not self.response_step
                    else _messages_from_step_input(self.response_step),
                )
            )

        return nodes

    def to_phase(self, live: LiveTraceContext | None) -> dict[str, Any]:
        label = f"Agent · turn {self.turn}"
        if self.tools:
            label = f"Agent · turn {self.turn}"
        return {
            "id": self.id,
            "type": "agent_turn",
            "turn": self.turn,
            "label": label,
            "state": self.state,
            "children": self.children(live),
        }


def _open_tool(
    tool_name: str,
    call_step: AgentStep | None,
    running_names: set[str],
) -> _ToolAcc:
    running = tool_name in running_names and call_step is None
    state: TraceState = "running" if running or call_step else "pending"
    return _ToolAcc(
        id=str(call_step.id) if call_step else f"tool-{tool_name}-pending",
        tool_name=tool_name,
        call_step=call_step,
        state=state,
    )


def _attach_tool_result(tools: list[_ToolAcc], step: AgentStep) -> list[_ToolAcc]:
    name = step.tool_name or ""
    next_tools = list(tools)
    idx = -1
    for i in range(len(next_tools) - 1, -1, -1):
        if next_tools[i].tool_name == name and next_tools[i].result_step is None:
            idx = i
            break
    if idx >= 0:
        t = next_tools[idx]
        next_tools[idx] = _ToolAcc(
            id=t.id,
            tool_name=t.tool_name,
            call_step=t.call_step,
            result_step=step,
            state="done",
        )
        return next_tools
    next_tools.append(
        _ToolAcc(
            id=str(step.id),
            tool_name=name,
            result_step=step,
            state="done",
        )
    )
    return next_tools


def _synthesis_phase(step: AgentStep) -> dict[str, Any]:
    prompt = _messages_from_step_input(step)
    return _apply_tokens(
        {
            "id": str(step.id),
            "type": "synthesis",
            "label": "Answer synthesis",
            "state": "done",
            "model": _resolve_model(step, None, None),
            "prompt": prompt,
            "output": _step_text(step),
        },
        _tokens_from_step_input(step),
    )


def _tail_before_presentation(tail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in tail if p.get("type") not in ("presentation",)]


def _presentation_children(
    turns: list[_TurnAcc],
    tail_before: list[dict[str, Any]],
    step: AgentStep | None,
    state: TraceState,
) -> list[dict[str, Any]]:
    """Build agent-turn-style children for the visual summary agent."""
    children: list[dict[str, Any]] = []

    for turn in turns:
        for child in turn.children(live=None):
            labeled = dict(child)
            labeled["id"] = f"pres-{turn.id}-{child['id']}"
            labeled["label"] = f"Turn {turn.turn} · {child.get('label') or 'Step'}"
            children.append(labeled)

    for phase in tail_before:
        if phase.get("type") == "synthesis":
            children.append(
                {
                    "id": f"pres-{phase['id']}",
                    "type": "llm_response",
                    "label": str(phase.get("label") or "Answer synthesis"),
                    "state": phase.get("state") or "done",
                    "model": phase.get("model"),
                    "prompt": phase.get("prompt"),
                    "output": phase.get("output") or "",
                    "prompt_tokens": phase.get("prompt_tokens"),
                    "completion_tokens": phase.get("completion_tokens"),
                    "total_tokens": phase.get("total_tokens"),
                }
            )
        elif phase.get("type") == "hitl":
            children.append(
                {
                    "id": f"pres-{phase['id']}",
                    "type": "hitl_embed",
                    "label": str(phase.get("label") or "Human approval"),
                    "state": phase.get("state") or "done",
                    "pending": phase.get("pending"),
                    "building": phase.get("building"),
                    "input": phase.get("input"),
                    "output": phase.get("output"),
                }
            )

    if step is not None:
        step_input = step.input if isinstance(step.input, dict) else {}
        evidence = step_input.get("agent_evidence")
        if isinstance(evidence, dict):
            for i, hit in enumerate(evidence.get("document_hits") or []):
                if not isinstance(hit, dict):
                    continue
                filename = str(hit.get("filename") or "document")
                children.append(
                    {
                        "id": f"pres-evidence-doc-{i}",
                        "type": "tool",
                        "label": f"Evidence · {filename}",
                        "tool_name": "search_documents",
                        "state": "done",
                        "output": [hit],
                    }
                )
            web_hits = evidence.get("web_hits") or []
            if web_hits:
                children.append(
                    {
                        "id": "pres-evidence-web",
                        "type": "tool",
                        "label": "Evidence · Web search",
                        "tool_name": "web_search",
                        "state": "done",
                        "output": {
                            "results": [
                                h for h in web_hits if isinstance(h, dict)
                            ],
                        },
                    }
                )

        llm_output = step_input.get("llm_output")
        output = step.output
        if llm_output is None and isinstance(output, dict):
            llm_output = output.get("plain_summary")
        layout = {
            "id": f"{step.id}-layout-llm",
            "type": "llm_response",
            "label": "Layout engine",
            "state": state,
            "model": _resolve_model(step, None, None),
            "prompt": step_input.get("messages") or step_input.get("prompt"),
            "output": str(llm_output or ""),
        }
        children.append(_apply_tokens(layout, _tokens_from_step_input(step)))

        if isinstance(output, dict) and output.get("type") == "generative_ui":
            children.append(
                {
                    "id": f"{step.id}-ui-output",
                    "type": "tool",
                    "label": "Generated UI",
                    "tool_name": "generative_ui",
                    "state": "done",
                    "output": output,
                }
            )
    elif state == "running":
        children.append(
            {
                "id": "presentation-layout-pending",
                "type": "llm_response",
                "label": "Layout engine",
                "state": "running",
                "model": settings.chat_model,
                "prompt": None,
                "output": "",
            }
        )

    return children


def _presentation_phase(
    step: AgentStep,
    *,
    turns: list[_TurnAcc],
    tail: list[dict[str, Any]],
    state: TraceState = "done",
) -> dict[str, Any]:
    step_input = step.input if isinstance(step.input, dict) else {}
    output = step.output
    blocks = output.get("blocks") if isinstance(output, dict) else None
    llm_output = step_input.get("llm_output")
    if llm_output is None and isinstance(output, dict):
        llm_output = output.get("plain_summary")
    tail_before = _tail_before_presentation(tail)
    item = {
        "id": str(step.id),
        "type": "presentation",
        "label": "Visual summary",
        "state": state,
        "model": _resolve_model(step, None, None),
        "output": output,
        "prompt": step_input.get("messages") or step_input.get("prompt"),
        "llm_output": llm_output,
        "agent_evidence": step_input.get("agent_evidence"),
        "children": _presentation_children(turns, tail_before, step, state),
        "block_count": len(blocks) if isinstance(blocks, list) else 0,
        "presentation_profile": (
            output.get("presentation_profile") if isinstance(output, dict) else None
        ),
    }
    return _apply_tokens(item, _tokens_from_step_input(step))


def _parse_steps(
    steps: list[AgentStep],
    running_tools: set[str],
) -> tuple[list[_TurnAcc], list[dict[str, Any]]]:
    """Parse steps without live context (fixed attach_tool_result)."""
    turns: list[_TurnAcc] = []
    tail: list[dict[str, Any]] = []
    presentation_approvals: list[AgentStep] = []
    current: _TurnAcc | None = None
    turn_index = 0

    def start_turn() -> _TurnAcc:
        nonlocal turn_index, current
        turn_index += 1
        current = _TurnAcc(id=f"turn-{turn_index}", turn=turn_index, state="done")
        return current

    for step in sorted(steps, key=lambda s: s.step_index):
        if step.type == "tool_call":
            if current is None:
                start_turn()
            assert current is not None
            current.tools.append(_open_tool(step.tool_name or "tool", step, running_tools))
            if any(t.state == "running" for t in current.tools):
                current.state = "running"
            continue

        if step.type == "tool_result":
            if current is None:
                start_turn()
            assert current is not None
            current.tools = _attach_tool_result(current.tools, step)
            continue

        if step.type == "thought":
            if current is None:
                start_turn()
            assert current is not None
            if any(t.result_step is None for t in current.tools):
                current.planning_step = step
                continue
            current.response_step = step
            current.state = "done"
            turns.append(current)
            current = None
            continue

        if step.type == "final":
            if current is None:
                start_turn()
            assert current is not None
            current.response_step = step
            current.state = "done"
            turns.append(current)
            current = None
            continue

        if step.type == "approval":
            if current is not None:
                current.state = "done"
                turns.append(current)
                current = None
            if step.tool_name == PRESENTATION_TOOL:
                presentation_approvals.append(step)
            else:
                waiting = _step_output_status(step) == "waiting_approval"
                tail.append(
                    {
                        "id": str(step.id),
                        "type": "hitl",
                        "label": "Human approval",
                        "state": "running" if waiting else "done",
                        "pending": waiting,
                        "building": False,
                        "input": step.input,
                        "output": step.output,
                    }
                )
            continue

        if step.type == "presentation" or _is_generative_ui(step.output):
            item = _presentation_phase(step, turns=turns, tail=tail, state="done")
            idx = next(
                (i for i, t in enumerate(tail) if t.get("type") == "presentation" and t.get("state") != "done"),
                -1,
            )
            if idx >= 0:
                tail[idx] = item
            else:
                tail.append(item)
            continue

        if step.type == "synthesis":
            tail.append(_synthesis_phase(step))

    if current is not None:
        if any(t.state != "done" for t in current.tools):
            current.state = "running"
        turns.append(current)

    if presentation_approvals:
        last = presentation_approvals[-1]
        approved = any(_step_output_status(s) == "approved" for s in presentation_approvals)
        rejected = any(_step_output_status(s) == "rejected" for s in presentation_approvals)
        waiting = not approved and not rejected
        hitl = {
            "id": f"hitl-{last.id}",
            "type": "hitl",
            "label": "Human approval · View in UI?",
            "state": "running" if waiting else "done",
            "pending": waiting,
            "building": False,
            "input": last.input,
            "output": last.output,
        }
        pres_idx = next((i for i, t in enumerate(tail) if t.get("type") == "presentation"), -1)
        if pres_idx >= 0:
            tail.insert(pres_idx, hitl)
        else:
            tail.append(hitl)

    return turns, tail


def _presentation_pending(run: AgentRun) -> bool:
    pending = run.pending_tool
    if not pending or not isinstance(pending, dict):
        return False
    return pending.get("name") == PRESENTATION_TOOL or pending.get("kind") == "presentation"


def _apply_run_overlays(
    phases: list[dict[str, Any]],
    run: AgentRun,
    live: LiveTraceContext | None,
    *,
    turns: list[_TurnAcc] | None = None,
    tail: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    out = list(phases)
    pres_pending = _presentation_pending(run) and run.status == "waiting_approval"
    has_pending_hitl = any(p.get("type") == "hitl" and p.get("pending") for p in out)

    if pres_pending and not has_pending_hitl:
        out.append(
            {
                "id": "hitl-pending",
                "type": "hitl",
                "label": "Human approval · View in UI?",
                "state": "running",
                "pending": True,
                "building": bool(live and live.approving),
            }
        )

    if live and live.approving and pres_pending:
        out = [
            (
                {**p, "building": True, "state": "running"}
                if p.get("type") == "hitl" and p.get("pending")
                else p
            )
            for p in out
        ]
        if not any(p.get("type") == "presentation" for p in out):
            out.append(
                {
                    "id": "presentation-pending",
                    "type": "presentation",
                    "label": "Visual summary",
                    "state": "running",
                    "model": settings.chat_model,
                    "children": _presentation_children(
                        turns or [],
                        _tail_before_presentation(tail or []),
                        None,
                        "running",
                    ),
                }
            )
        else:
            out = [
                (
                    {**p, "state": "running"}
                    if p.get("type") == "presentation" and p.get("state") != "done"
                    else p
                )
                for p in out
            ]

    if live and live.llm_running and live.current_turn_id and out:
        for i, phase in enumerate(out):
            if phase.get("type") != "agent_turn":
                continue
            if phase.get("state") == "running" or (
                i == len([p for p in out if p.get("type") == "agent_turn"]) - 1
            ):
                phase = dict(phase)
                phase["state"] = "running"
                phase["llm_turn_id"] = live.current_turn_id
                out[i] = phase
                break

    if live and live.running_tool_names and out:
        running_set = set(live.running_tool_names)
        for i, phase in enumerate(out):
            if phase.get("type") != "agent_turn":
                continue
            children = []
            for child in phase.get("children") or []:
                if child.get("type") == "tool" and child.get("tool_name") in running_set:
                    child = {**child, "state": "running"}
                children.append(child)
            phase = {**phase, "children": children, "state": "running"}
            out[i] = phase

    if run.status == "running" and out:
        for i in range(len(out) - 1, -1, -1):
            if out[i].get("type") == "agent_turn":
                t = dict(out[i])
                t["state"] = "running"
                out[i] = t
                break

    return out


def _phase_done(phase: dict[str, Any]) -> bool:
    if phase.get("state") != "done":
        return False
    if phase.get("type") == "agent_turn":
        return all(c.get("state") == "done" for c in phase.get("children") or [])
    if phase.get("type") == "hitl" and phase.get("pending"):
        return False
    return True


def _trim_children(children: list[dict[str, Any]], live: bool) -> list[dict[str, Any]]:
    if not live:
        return children
    visible: list[dict[str, Any]] = []
    for child in children:
        if child.get("type") == "tool" and child.get("state") == "pending":
            break
        visible.append(child)
        if child.get("state") != "done":
            break
    return visible


def _trim_phases(phases: list[dict[str, Any]], live: bool) -> list[dict[str, Any]]:
    if not live:
        return phases
    visible: list[dict[str, Any]] = []
    for phase in phases:
        p = dict(phase)
        if p.get("type") == "agent_turn":
            p["children"] = _trim_children(p.get("children") or [], live=True)
            tools = [c for c in p.get("children") or [] if c.get("type") == "tool"]
            tools_ready = not tools or all(t.get("state") == "done" for t in tools)
            if tools and not tools_ready:
                visible.append(p)
                break
        visible.append(p)
        if not _phase_done(p):
            break
    return visible


def _token_fields_from_node(node: dict[str, Any]) -> tuple[int, int, int]:
    p = int(node.get("prompt_tokens") or 0)
    c = int(node.get("completion_tokens") or 0)
    t = int(node.get("total_tokens") or 0)
    if t <= 0 and (p > 0 or c > 0):
        t = p + c
    return p, c, t


def _sum_trace_tokens(phases: list[dict[str, Any]]) -> dict[str, int]:
    """Sum tokens across every LLM call in the execution (agent, synthesis, visual)."""
    prompt_total = 0
    completion_total = 0
    total = 0
    seen: set[str] = set()

    def consume(node: dict[str, Any]) -> None:
        nonlocal prompt_total, completion_total, total
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen:
            return
        p, c, t = _token_fields_from_node(node)
        if p == 0 and c == 0 and t == 0:
            return
        seen.add(node_id)
        prompt_total += p
        completion_total += c
        total += t

    for phase in phases:
        ptype = phase.get("type")
        if ptype == "agent_turn":
            for child in phase.get("children") or []:
                if child.get("type") == "llm_response":
                    consume(child)
        elif ptype == "synthesis":
            consume(phase)
        elif ptype == "presentation":
            layout_nodes = [
                c
                for c in phase.get("children") or []
                if c.get("type") == "llm_response"
                and str(c.get("id") or "").endswith("-layout-llm")
            ]
            if layout_nodes:
                for child in layout_nodes:
                    consume(child)
            else:
                consume(phase)

    if total <= 0 and (prompt_total > 0 or completion_total > 0):
        total = prompt_total + completion_total

    summary: dict[str, int] = {}
    if prompt_total > 0:
        summary["prompt_tokens"] = prompt_total
    if completion_total > 0:
        summary["completion_tokens"] = completion_total
    if total > 0:
        summary["total_tokens"] = total
    return summary


def _active_phase_id(phases: list[dict[str, Any]]) -> str | None:
    for phase in phases:
        if not _phase_done(phase):
            return str(phase.get("id"))
        if phase.get("type") == "agent_turn":
            for child in phase.get("children") or []:
                if child.get("state") != "done":
                    return str(child.get("id"))
    return phases[-1]["id"] if phases else None


def build_execution_trace(
    run: AgentRun,
    *,
    live: LiveTraceContext | None = None,
) -> dict[str, Any]:
    steps = sorted(run.steps or [], key=lambda s: s.step_index)
    running_tools = set(live.running_tool_names if live else [])
    turns, tail = _parse_steps(steps, running_tools)

    if live and live.current_turn_id and turns:
        last = turns[-1]
        if last.state == "running" or live.llm_running:
            last.llm_turn_id = live.current_turn_id
            if live.llm_running:
                last.state = "running"

    phases: list[dict[str, Any]] = [
        {
            "id": "goal",
            "type": "goal",
            "label": "Input goal",
            "state": "done",
            "goal": run.goal or "",
        }
    ]

    for turn in turns:
        phase = turn.to_phase(live)
        if live and turn.llm_turn_id:
            phase["llm_turn_id"] = turn.llm_turn_id
        phases.append(phase)

    phases.extend(tail)
    phases = _apply_run_overlays(phases, run, live, turns=turns, tail=tail)

    is_complete = run.status in COMPLETE_STATUSES
    live_mode = not is_complete and (
        run.status in ("running", "waiting_approval")
        or (live is not None and (live.llm_running or live.approving))
    )
    token_usage = _sum_trace_tokens(phases)
    if not token_usage and run.token_usage:
        token_usage = {"total_tokens": int(run.token_usage)}
    visible = _trim_phases(phases, live=live_mode)

    return {
        "goal": run.goal or "",
        "phases": visible,
        "active_phase_id": _active_phase_id(visible),
        "is_complete": is_complete,
        "token_usage": token_usage or None,
    }


def emit_execution_trace(
    on_event: Any,
    run: AgentRun,
    live: LiveTraceContext | None = None,
) -> dict[str, Any]:
    trace = build_execution_trace(run, live=live)
    if on_event:
        on_event(
            "trace",
            {
                "execution_trace": trace,
                "run_id": str(run.id),
                "status": run.status,
            },
        )
    return trace