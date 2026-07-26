"""LLM-authored diagrams for topic study-sheet sections.

Unlike ``app.mcp.drawio.mermaid_from_structured`` (regex arrow/bullet
chaining — always a linear flowchart), this asks the model to decide, per
section, whether a diagram helps and what shape it should take. Mermaid's
flowchart syntax covers trees and graphs (parent->child edges, cycles,
subgraphs) as well as linear flows, so a DSA section like "Binary Search
Tree — Insert" can come back as an actual tree instead of a forced chain.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.agents.visual_summary.llm_json import chat_json
from app.usage import estimate_tokens, log_usage

_MAX_SECTIONS_PER_CALL = 12
_MAX_SECTION_CHARS = 1200

SECTION_DIAGRAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_index": {"type": "integer"},
                    "needs_diagram": {"type": "boolean"},
                    "diagram_kind": {"type": "string"},
                    "mermaid": {"type": "string"},
                },
                "required": [
                    "section_index",
                    "needs_diagram",
                    "diagram_kind",
                    "mermaid",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sections"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You are a diagramming assistant for a study-sheet generator. For each "
    "numbered section you are given (heading + body/bullets), decide whether "
    "a diagram would help a learner more than plain text, and if so author it "
    "in Mermaid syntax.\n\n"
    "Pick the diagram shape that actually matches the content — do not force "
    "everything into a left-to-right chain:\n"
    "- A hierarchy or tree (e.g. binary search tree, org chart, taxonomy): "
    "flowchart TD with parent-->child edges shaped like a tree.\n"
    "- A graph with branches/cycles (e.g. state machines, graph traversal): "
    "flowchart TD or graph LR, edges may branch or cycle.\n"
    "- A linear process/pipeline: flowchart LR or TD, one edge per step.\n"
    "- An interaction between actors/services: sequenceDiagram.\n"
    "- An array/pointer structure (e.g. linked list, two-pointer technique): "
    "flowchart LR with each element as a node.\n\n"
    "Set needs_diagram=false for sections that are pure prose, a table, a "
    "checklist, or best-practices — those already read fine as text and a "
    "forced diagram is noise. Keep node labels short (a few words). Output "
    "must be valid Mermaid — no markdown code fences, no commentary."
)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _section_text(sec: dict[str, Any]) -> str:
    heading = str(sec.get("heading") or "").strip()
    body = str(sec.get("body") or "").strip()
    bullets = sec.get("bullets") or []
    lines = [heading] if heading else []
    if body:
        lines.append(body)
    for b in bullets if isinstance(bullets, list) else []:
        lines.append(f"- {b}")
    text = "\n".join(lines)
    return text[:_MAX_SECTION_CHARS]


def author_section_diagrams(
    sections: list[tuple[int, dict[str, Any]]],
    *,
    goal: str = "",
    db: Session | None = None,
    user_id: Any = None,
    workspace_id: Any = None,
) -> dict[int, dict[str, Any]]:
    """
    One batched LLM call: decide per section whether a diagram helps and
    author it in Mermaid.

    ``sections`` is a list of (1-based section_index, section dict) — the
    same pairs ``build_topic_study_sheet_plan`` iterates. Returns
    section_index -> {"diagram_kind": str, "mermaid": str} for sections the
    model marked ``needs_diagram``. Never raises — on any LLM/parse failure
    returns {} so callers keep today's rendering for every section.
    """
    picked = sections[:_MAX_SECTIONS_PER_CALL]
    if not picked:
        return {}

    prompt_sections = [
        {"section_index": idx, "content": _section_text(sec)} for idx, sec in picked
    ]
    prompt = (
        f"Goal: {goal[:200]}\n\n"
        "Sections (JSON):\n"
        f"{json.dumps(prompt_sections, ensure_ascii=False)}\n\n"
        "Return one entry per section_index, in the same order."
    )

    try:
        resp = chat_json(
            _client(),
            model=settings.visual_summary_model,
            system=_SYSTEM_PROMPT,
            prompt=prompt,
            schema_name="section_diagrams",
            schema=SECTION_DIAGRAM_SCHEMA,
            temperature=0.1,
        )
    except Exception:
        return {}

    raw = (resp.choices[0].message.content or "{}").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    out: dict[int, dict[str, Any]] = {}
    valid_indices = {idx for idx, _ in picked}
    for entry in parsed.get("sections") or []:
        if not isinstance(entry, dict) or not entry.get("needs_diagram"):
            continue
        try:
            idx = int(entry.get("section_index"))
        except (TypeError, ValueError):
            continue
        if idx not in valid_indices:
            continue
        mermaid = str(entry.get("mermaid") or "").strip()
        if not mermaid:
            continue
        out[idx] = {
            "diagram_kind": str(entry.get("diagram_kind") or "flowchart")[:40],
            "mermaid": mermaid,
        }

    usage = getattr(resp, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens == 0 and completion_tokens == 0:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(raw)
    if db is not None and workspace_id is not None:
        log_usage(
            db,
            user_id=user_id,
            workspace_id=workspace_id,
            kind="visual_summary_section_diagrams",
            model=settings.visual_summary_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            meta={"goal": goal[:200], "sections_authored": len(out)},
        )

    return out
