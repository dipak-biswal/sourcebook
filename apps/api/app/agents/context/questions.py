"""Build structured questions for the context HITL form.

Templates always available; LLM path (llm.py) may refine phrasing.
"""

from __future__ import annotations

from typing import Any

from app.agents.context.readiness import Gap
from app.agents.visual_summary.workspace.context import WorkspaceContextPacket

# Shared UI contract — keep in sync with frontend AgentApprovalCard.
Question = dict[str, Any]


def _text(
    qid: str,
    prompt: str,
    *,
    required: bool = False,
    placeholder: str = "",
) -> Question:
    q: Question = {
        "id": qid,
        "prompt": prompt,
        "input": "text",
        "required": required,
    }
    if placeholder:
        q["placeholder"] = placeholder
    return q


def _checkbox(
    qid: str,
    prompt: str,
    options: list[dict[str, str]],
    *,
    required: bool = False,
    allow_multiple: bool = False,
) -> Question:
    return {
        "id": qid,
        "prompt": prompt,
        "input": "checkbox",
        "options": options,
        "required": required,
        "allow_multiple": allow_multiple,
    }


def template_questions_for_gaps(
    gaps: list[Gap],
    packet: WorkspaceContextPacket,
    goal: str,
    *,
    max_questions: int = 4,
) -> list[Question]:
    """Deterministic questions keyed by gap id (stable for tests + fallback)."""
    gap_ids = {g.id for g in gaps}
    out: list[Question] = []

    if "vague_goal" in gap_ids or "research_unscoped" in gap_ids:
        out.append(
            _text(
                "topic_scope",
                "What should we focus on for this run?",
                required=True,
                placeholder="e.g. HTTP request/response cycle for beginners",
            )
        )

    if "research_unscoped" in gap_ids or "vague_goal" in gap_ids:
        out.append(
            _checkbox(
                "level",
                "What level should the answer target?",
                [
                    {"id": "beginner", "label": "Beginner"},
                    {"id": "intermediate", "label": "Intermediate"},
                    {"id": "advanced", "label": "Advanced"},
                ],
                required=False,
                allow_multiple=False,
            )
        )

    if "audience_unknown" in gap_ids:
        out.append(
            _checkbox(
                "audience",
                "Who is this for?",
                [
                    {"id": "myself", "label": "Myself"},
                    {"id": "team", "label": "My team"},
                    {"id": "interview", "label": "Interview prep"},
                    {"id": "client", "label": "Client / stakeholder"},
                ],
                required=False,
                allow_multiple=False,
            )
        )

    if "docs_implied" in gap_ids or (
        "research_unscoped" in gap_ids and not packet.evidence.documents_ready
    ):
        out.append(
            _checkbox(
                "document_plan",
                "How should we get evidence?",
                [
                    {"id": "upload", "label": "I'll upload documents"},
                    {"id": "web", "label": "Use the web"},
                    {"id": "both", "label": "Both"},
                ],
                required=False,
                allow_multiple=False,
            )
        )

    if "url_missing" in gap_ids or "research_unscoped" in gap_ids:
        out.append(
            _text(
                "urls",
                "Any URLs we should use? (optional, one per line or comma-separated)",
                required="url_missing" in gap_ids,
                placeholder="https://…",
            )
        )

    if "thin_workspace" in gap_ids and "topic_scope" not in {q["id"] for q in out}:
        out.append(
            _text(
                "workspace_framing",
                "In one sentence, what is this workspace for?",
                required=False,
                placeholder="e.g. Study distributed systems from my notes",
            )
        )

    if "research_unscoped" in gap_ids and len(out) < max_questions:
        out.append(
            _text(
                "must_cover",
                "Any must-cover subtopics or constraints? (optional)",
                required=False,
                placeholder="e.g. skip history, focus on practical examples",
            )
        )

    seen: set[str] = set()
    unique: list[Question] = []
    for q in out:
        qid = str(q.get("id") or "")
        if not qid or qid in seen:
            continue
        seen.add(qid)
        unique.append(q)
        if len(unique) >= max_questions:
            break

    if not unique and gaps:
        unique.append(
            _text(
                "topic_scope",
                "What else should the agent know for this goal?",
                required=True,
                placeholder="Add detail so the answer fits your needs",
            )
        )

    _ = goal  # reserved for future personalization
    return unique


def normalize_questions(raw: list[Any], *, max_questions: int = 4) -> list[Question]:
    """Sanitize LLM or template output into the UI contract."""
    out: list[Question] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not qid or not prompt or qid in seen:
            continue
        kind = str(item.get("input") or "text").strip().lower()
        if kind not in ("text", "checkbox"):
            kind = "text"
        q: Question = {
            "id": qid[:64],
            "prompt": prompt[:400],
            "input": kind,
            "required": bool(item.get("required")),
        }
        ph = item.get("placeholder")
        if isinstance(ph, str) and ph.strip():
            q["placeholder"] = ph.strip()[:200]
        if kind == "checkbox":
            opts_raw = item.get("options") or []
            options: list[dict[str, str]] = []
            for opt in opts_raw:
                if not isinstance(opt, dict):
                    continue
                oid = str(opt.get("id") or "").strip()
                label = str(opt.get("label") or oid).strip()
                if oid and label:
                    options.append({"id": oid[:64], "label": label[:120]})
            if len(options) < 2:
                q["input"] = "text"
            else:
                q["options"] = options[:8]
                q["allow_multiple"] = bool(item.get("allow_multiple"))
        seen.add(qid)
        out.append(q)
        if len(out) >= max_questions:
            break
    return out


def default_form_title(gaps: list[Gap]) -> str:
    if any(g.severity == "high" for g in gaps):
        return "A bit more context will improve the answer"
    return "Optional details to focus this run"


def default_form_subtitle() -> str:
    return "Answer what you can — skip optional fields if unsure."
