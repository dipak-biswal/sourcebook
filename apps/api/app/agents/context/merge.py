"""Merge HITL answers into a run-scoped context snapshot for the main agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CollectedContextSnapshot:
    topic_focus: str = ""
    audience: str = ""
    level: str = ""
    urls: list[str] = field(default_factory=list)
    document_plan: str = ""
    workspace_framing: str = ""
    must_cover: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_empty(self) -> bool:
        return not any(
            [
                self.topic_focus,
                self.audience,
                self.level,
                self.urls,
                self.document_plan,
                self.workspace_framing,
                self.must_cover,
                self.extra,
            ]
        )


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(parts)
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    parts: list[str] = []
    for line in text.replace(",", "\n").splitlines():
        p = line.strip()
        if p:
            parts.append(p)
    return parts


_LABELS: dict[str, str] = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
    "myself": "Myself",
    "team": "My team",
    "interview": "Interview prep",
    "client": "Client / stakeholder",
    "upload": "I'll upload documents",
    "web": "Use the web",
    "both": "Both documents and web",
}


def _pretty(value: str) -> str:
    if not value:
        return ""
    if "," in value:
        return ", ".join(
            _LABELS.get(p.strip(), p.strip()) for p in value.split(",")
        )
    return _LABELS.get(value, value)


def answers_to_snapshot(
    answers: dict[str, Any] | None,
    *,
    questions: list[dict[str, Any]] | None = None,
) -> CollectedContextSnapshot:
    """
    Convert form answers (question_id → string | string[]) into a snapshot.

    Unknown question ids land in ``extra`` so LLM-generated fields still frame.
    """
    answers = answers or {}
    known_ids = {
        "topic_scope",
        "level",
        "audience",
        "document_plan",
        "urls",
        "workspace_framing",
        "must_cover",
    }
    option_labels: dict[str, dict[str, str]] = {}
    for q in questions or []:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or "")
        opts = q.get("options") or []
        if qid and isinstance(opts, list):
            option_labels[qid] = {
                str(o.get("id")): str(o.get("label") or o.get("id"))
                for o in opts
                if isinstance(o, dict) and o.get("id")
            }

    def resolve(qid: str, raw: Any) -> str:
        text = _as_str(raw)
        if not text:
            return ""
        labels = option_labels.get(qid) or {}
        if labels:
            parts = [p.strip() for p in text.split(",") if p.strip()]
            return ", ".join(labels.get(p, _pretty(p)) for p in parts)
        return _pretty(text)

    snap = CollectedContextSnapshot(
        topic_focus=resolve("topic_scope", answers.get("topic_scope")),
        audience=resolve("audience", answers.get("audience")),
        level=resolve("level", answers.get("level")),
        urls=_as_list(answers.get("urls")),
        document_plan=resolve("document_plan", answers.get("document_plan")),
        workspace_framing=resolve(
            "workspace_framing", answers.get("workspace_framing")
        ),
        must_cover=resolve("must_cover", answers.get("must_cover")),
    )

    for key, val in answers.items():
        if key in known_ids:
            continue
        text = resolve(key, val)
        if text:
            snap.extra[str(key)[:64]] = text[:500]

    return snap


def format_collected_context(snapshot: CollectedContextSnapshot | None) -> str:
    """Prompt block injected after WORKSPACE CONTEXT for the main agent."""
    if snapshot is None or snapshot.is_empty():
        return ""
    lines = ["COLLECTED RUN CONTEXT (user-confirmed for this run):"]
    if snapshot.topic_focus:
        lines.append(f"- Topic focus: {snapshot.topic_focus}")
    if snapshot.audience:
        lines.append(f"- Audience: {snapshot.audience}")
    if snapshot.level:
        lines.append(f"- Level: {snapshot.level}")
    if snapshot.urls:
        lines.append(f"- URLs to prefer: {', '.join(snapshot.urls)}")
    if snapshot.document_plan:
        lines.append(f"- Document plan: {snapshot.document_plan}")
    if snapshot.workspace_framing:
        lines.append(f"- Workspace framing (this run): {snapshot.workspace_framing}")
    if snapshot.must_cover:
        lines.append(f"- Must-cover / constraints: {snapshot.must_cover}")
    for k, v in snapshot.extra.items():
        label = k.replace("_", " ")
        lines.append(f"- {label}: {v}")
    lines.append(
        "Treat this as authoritative user intent for this run. "
        "Prefer these URLs/documents when researching. "
        "Do not invent details the user did not provide."
    )
    return "\n".join(lines)


def snapshot_from_dict(data: dict[str, Any] | None) -> CollectedContextSnapshot | None:
    if not data or not isinstance(data, dict):
        return None
    urls = data.get("urls") or []
    if not isinstance(urls, list):
        urls = _as_list(urls)
    extra = data.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    snap = CollectedContextSnapshot(
        topic_focus=str(data.get("topic_focus") or "").strip(),
        audience=str(data.get("audience") or "").strip(),
        level=str(data.get("level") or "").strip(),
        urls=[str(u).strip() for u in urls if str(u).strip()],
        document_plan=str(data.get("document_plan") or "").strip(),
        workspace_framing=str(data.get("workspace_framing") or "").strip(),
        must_cover=str(data.get("must_cover") or "").strip(),
        extra={str(k): str(v) for k, v in extra.items() if str(v).strip()},
    )
    return None if snap.is_empty() else snap
