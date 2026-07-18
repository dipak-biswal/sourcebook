"""Workspace-derived context for agents (no vertical hardcoding).

Builds a WorkspaceContextPacket from workspace name, description, tags, and
documents. Heuristic v1 — no LLM call on the agent hot path.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Document, Workspace

DERIVATION_VERSION = 1

_DEFAULT_AFFORDANCES = (
    "overview",
    "highlights",
    "self_check",
)

# (keywords, affordance_ids) — order matters for ranking
_AFFORDANCE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("learn", "understand", "concept", "definition", "study", "course", "tutorial"),
        ("concept_glossary", "ordered_guide", "self_check", "topic_filter"),
    ),
    (
        ("guide", "checklist", "steps", "how to", "howto", "update", "improve", "edit"),
        ("ordered_guide", "priority_alert", "highlights"),
    ),
    (
        ("compare", "vs", "versus", "requirement", "fit", "gap", "align", "match"),
        ("comparison_matrix", "priority_alert", "highlights"),
    ),
    (
        ("skill", "level", "strength", "proficiency", "competenc"),
        ("qualitative_levels", "comparison_matrix"),
    ),
    (
        ("faq", "question", "interview", "misconception", "quiz"),
        ("self_check",),
    ),
    (
        ("priority", "warning", "start here", "critical", "risk"),
        ("priority_alert",),
    ),
    (
        ("history", "timeline", "career path", "dates", "milestone"),
        ("timeline",),
    ),
    (
        ("kpi", "metric", "stats", "numbers", "dashboard"),
        ("metrics",),
    ),
    (
        ("design", "architect", "system", "tradeoff", "trade-off"),
        ("concept_glossary", "comparison_matrix", "ordered_guide", "self_check"),
    ),
    (
        ("research", "notes", "reference", "lookup"),
        ("concept_glossary", "topic_filter", "highlights"),
    ),
)

_TONE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("learn", "study", "course", "teach", "tutorial", "student"), "instructional"),
    (("decide", "compare", "evaluate", "rfp", "bid", "gap", "analysis"), "analytical"),
    (("executive", "brief", "board", "stakeholder", "summary only"), "executive"),
    (("personal", "journal", "casual", "notes for me"), "casual"),
)

_EXTERNAL_OFF: tuple[str, ...] = (
    "private",
    "confidential",
    "internal only",
    "no web",
    "offline",
    "do not search",
    "secrets",
    "nda",
)

_EXTERNAL_ON: tuple[str, ...] = (
    "market",
    "industry",
    "benchmark",
    "external",
    "web",
    "public",
    "interview",
    "current",
    "trends",
)


@dataclass
class ToolPolicy:
    external_context_ok: bool = True
    max_search_documents: int = 2
    max_web_search: int = 1
    max_fetch_url: int = 2


@dataclass
class WorkspaceDerived:
    outcome_phrase: str = "help with tasks in this workspace"
    audience_phrase: str = "the workspace owner"
    success_criteria: str = "a clear, evidence-grounded answer to the goal"
    tone: str = "analytical"
    external_context_ok: bool = True
    answer_sections: list[str] = field(default_factory=list)
    visual_affordances: list[str] = field(default_factory=list)
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
    # LLM profiler extras (empty on heuristic-only derivation)
    domain_label: str = ""
    planner_example: dict[str, Any] | None = None


@dataclass
class WorkspaceEvidence:
    document_count: int = 0
    documents_ready: list[str] = field(default_factory=list)
    documents_pending: list[str] = field(default_factory=list)
    filename_hints: list[str] = field(default_factory=list)


@dataclass
class WorkspaceIdentity:
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class WorkspaceContextMeta:
    confidence: str = "low"  # low | medium | high
    derivation_version: int = DERIVATION_VERSION


@dataclass
class WorkspaceContextPacket:
    identity: WorkspaceIdentity = field(default_factory=WorkspaceIdentity)
    evidence: WorkspaceEvidence = field(default_factory=WorkspaceEvidence)
    derived: WorkspaceDerived = field(default_factory=WorkspaceDerived)
    meta: WorkspaceContextMeta = field(default_factory=WorkspaceContextMeta)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _str_field(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key)
    return str(value).strip() if isinstance(value, str) else default


def _str_list_field(data: dict[str, Any], key: str) -> list[str]:
    raw = data.get(key)
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def packet_from_dict(data: dict[str, Any]) -> WorkspaceContextPacket:
    """Rebuild a packet from to_dict() output (e.g. the workspace cache row)."""
    data = data if isinstance(data, dict) else {}
    identity_raw = data.get("identity") or {}
    evidence_raw = data.get("evidence") or {}
    derived_raw = data.get("derived") or {}
    meta_raw = data.get("meta") or {}
    policy_raw = derived_raw.get("tool_policy") or {}

    policy = ToolPolicy(
        external_context_ok=bool(policy_raw.get("external_context_ok", True)),
        max_search_documents=int(policy_raw.get("max_search_documents") or 2),
        max_web_search=int(policy_raw.get("max_web_search") or 1),
        max_fetch_url=int(policy_raw.get("max_fetch_url") or 2),
    )
    planner_example = derived_raw.get("planner_example")
    derived = WorkspaceDerived(
        outcome_phrase=_str_field(
            derived_raw, "outcome_phrase", "help with tasks in this workspace"
        ),
        audience_phrase=_str_field(
            derived_raw, "audience_phrase", "the workspace owner"
        ),
        success_criteria=_str_field(
            derived_raw,
            "success_criteria",
            "a clear, evidence-grounded answer to the goal",
        ),
        tone=_str_field(derived_raw, "tone", "analytical") or "analytical",
        external_context_ok=bool(derived_raw.get("external_context_ok", True)),
        answer_sections=_str_list_field(derived_raw, "answer_sections"),
        visual_affordances=_str_list_field(derived_raw, "visual_affordances"),
        tool_policy=policy,
        domain_label=_str_field(derived_raw, "domain_label"),
        planner_example=planner_example if isinstance(planner_example, dict) else None,
    )
    return WorkspaceContextPacket(
        identity=WorkspaceIdentity(
            name=_str_field(identity_raw, "name"),
            description=_str_field(identity_raw, "description"),
            tags=_str_list_field(identity_raw, "tags"),
        ),
        evidence=WorkspaceEvidence(
            document_count=int(evidence_raw.get("document_count") or 0),
            documents_ready=_str_list_field(evidence_raw, "documents_ready"),
            documents_pending=_str_list_field(evidence_raw, "documents_pending"),
            filename_hints=_str_list_field(evidence_raw, "filename_hints"),
        ),
        derived=derived,
        meta=WorkspaceContextMeta(
            confidence=_str_field(meta_raw, "confidence", "low") or "low",
            derivation_version=int(
                meta_raw.get("derivation_version") or DERIVATION_VERSION
            ),
        ),
    )


def _blob(*parts: str) -> str:
    return " ".join(p.strip().lower() for p in parts if p and p.strip())


def _tokenize_filename(name: str) -> list[str]:
    stem = re.sub(r"\.[a-z0-9]{1,8}$", "", name, flags=re.I)
    tokens = re.split(r"[\s_\-.]+", stem.lower())
    return [t for t in tokens if len(t) >= 3][:8]


def _match_any(blob: str, keywords: tuple[str, ...]) -> bool:
    return any(k in blob for k in keywords)


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _derive_affordances(blob: str, tags: list[str]) -> list[str]:
    found: list[str] = list(_DEFAULT_AFFORDANCES)
    tag_blob = " ".join(tags).lower()
    combined = f"{blob} {tag_blob}"
    for keywords, affordances in _AFFORDANCE_RULES:
        if _match_any(combined, keywords):
            found.extend(affordances)
    if len(tags) >= 2 or "theme" in combined or "topic" in combined:
        found.append("topic_filter")
    return _ordered_unique(found)


def _derive_tone(blob: str) -> str:
    for keywords, tone in _TONE_RULES:
        if _match_any(blob, keywords):
            return tone
    return "analytical"


def _derive_external_ok(blob: str, evidence_style: str) -> bool:
    if _match_any(blob, _EXTERNAL_OFF):
        return False
    if _match_any(blob, _EXTERNAL_ON):
        return True
    # Thin private corpus → prefer docs only unless description invites outside context
    if evidence_style in ("empty", "thin") and not _match_any(
        blob, ("research", "learn", "market", "interview", "benchmark")
    ):
        return True  # still allow for general knowledge unless private markers
    return True


def _derive_outcome(description: str, name: str) -> str:
    text = (description or "").strip()
    if not text:
        return f"support tasks in workspace “{name or 'Untitled'}”"
    # First sentence or first 160 chars as plain outcome
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(first) > 180:
        first = first[:177].rstrip() + "…"
    return first


def _derive_success(description: str, blob: str) -> str:
    m = re.search(
        r"success(?: looks like)?\s*[:\-–]\s*(.+?)(?:\n|$)",
        description or "",
        flags=re.I,
    )
    if m:
        return m.group(1).strip()[:200]
    if _match_any(blob, ("learn", "understand", "study", "design")):
        return "user can explain key ideas and apply them to the goal"
    if _match_any(blob, ("compare", "gap", "fit", "requirement")):
        return "user has a clear comparison and prioritized next actions"
    if _match_any(blob, ("guide", "checklist", "update", "improve")):
        return "user has an ordered checklist grounded in workspace documents"
    return "a clear, evidence-grounded answer to the goal"


def _derive_audience(description: str, blob: str) -> str:
    m = re.search(r"audience\s*[:\-–]\s*(.+?)(?:\n|$)", description or "", flags=re.I)
    if m:
        return m.group(1).strip()[:120]
    if _match_any(blob, ("team", "client", "stakeholder", "executive")):
        if "client" in blob:
            return "client or external stakeholder"
        if "executive" in blob or "board" in blob:
            return "executive audience"
        return "team"
    return "the workspace owner (self)"


def _derive_answer_sections(blob: str, affordances: list[str]) -> list[str]:
    sections = ["Overview"]
    if "concept_glossary" in affordances or _match_any(
        blob, ("learn", "concept", "definition")
    ):
        sections.append("Core concepts")
    if "comparison_matrix" in affordances:
        sections.append("Comparison")
    if "ordered_guide" in affordances:
        sections.append("Steps / checklist")
    if "qualitative_levels" in affordances:
        sections.append("Strengths and gaps")
    if _match_any(blob, ("design", "architect", "tradeoff")):
        sections.append("Design approach")
    if "self_check" in affordances:
        sections.append("FAQ / self-check")
    sections.append("Next steps")
    return _ordered_unique(sections)


def _tool_policy_for(ready: int, pending: int, external_ok: bool) -> ToolPolicy:
    """Evidence-driven tool budgets — single source of truth."""
    style = _evidence_style(ready, pending)
    max_search = 3 if style == "corpus" else 2
    if not external_ok:
        return ToolPolicy(
            external_context_ok=False,
            max_search_documents=max_search,
            max_web_search=0,
            max_fetch_url=0,
        )
    # No ready documents → web research is the only evidence path; widen budgets.
    research = ready <= 0
    return ToolPolicy(
        external_context_ok=True,
        max_search_documents=max_search,
        max_web_search=3 if research else 1,
        max_fetch_url=3 if research else 2,
    )


def _evidence_style(ready: int, pending: int) -> str:
    if ready <= 0 and pending <= 0:
        return "empty"
    if ready == 0 and pending > 0:
        return "thin"
    if ready == 1:
        return "single_doc"
    if ready <= 3:
        return "thin"
    return "corpus"


def derive_workspace_context(
    *,
    name: str,
    description: str | None,
    tags: list[str] | None,
    document_rows: list[tuple[str, str]],
) -> WorkspaceContextPacket:
    """
    Pure derivation from workspace fields + (filename, status) document rows.
    """
    desc = (description or "").strip()
    tag_list = [str(t).strip() for t in (tags or []) if t and str(t).strip()]
    ready = [fn for fn, st in document_rows if (st or "").lower() == "ready"]
    pending = [
        fn
        for fn, st in document_rows
        if (st or "").lower() in ("uploaded", "queued", "processing")
    ]
    hints: list[str] = []
    for fn in ready[:12]:
        hints.extend(_tokenize_filename(fn))
    hints = _ordered_unique(hints)[:24]

    identity = WorkspaceIdentity(name=(name or "").strip(), description=desc, tags=tag_list)
    evidence = WorkspaceEvidence(
        document_count=len(document_rows),
        documents_ready=ready[:20],
        documents_pending=pending[:20],
        filename_hints=hints,
    )

    if not desc and not tag_list:
        confidence = "low"
        blob = _blob(name, " ".join(hints))
    elif not desc:
        confidence = "medium"
        blob = _blob(name, " ".join(tag_list), " ".join(hints))
    else:
        confidence = "high" if len(desc) >= 40 else "medium"
        blob = _blob(name, desc, " ".join(tag_list), " ".join(hints))

    style = _evidence_style(len(ready), len(pending))
    affordances = _derive_affordances(blob, tag_list)
    tone = _derive_tone(blob)
    external_ok = _derive_external_ok(blob, style)
    # Private / confidential → no web even if other signals
    if _match_any(blob, _EXTERNAL_OFF):
        external_ok = False

    derived = WorkspaceDerived(
        outcome_phrase=_derive_outcome(desc, name),
        audience_phrase=_derive_audience(desc, blob),
        success_criteria=_derive_success(desc, blob),
        tone=tone,
        external_context_ok=external_ok,
        answer_sections=_derive_answer_sections(blob, affordances),
        visual_affordances=affordances,
        tool_policy=_tool_policy_for(len(ready), len(pending), external_ok),
    )
    return WorkspaceContextPacket(
        identity=identity,
        evidence=evidence,
        derived=derived,
        meta=WorkspaceContextMeta(confidence=confidence, derivation_version=DERIVATION_VERSION),
    )


def resolve_workspace_context(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
) -> WorkspaceContextPacket:
    """
    Load workspace + documents and derive a context packet.

    Uses the cached LLM-profiled packet when the workspace is unchanged;
    otherwise profiles (when enabled) with the keyword heuristic as fallback.
    """
    ws = db.get(Workspace, workspace_id)
    rows = (
        db.query(Document.filename, Document.status)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .limit(50)
        .all()
    )
    doc_rows = [(str(fn or ""), str(st or "")) for fn, st in rows]
    if not ws:
        return derive_workspace_context(
            name="",
            description=None,
            tags=None,
            document_rows=doc_rows,
        )
    tags = ws.tags if isinstance(ws.tags, list) else None
    heuristic = derive_workspace_context(
        name=ws.name or "",
        description=ws.description,
        tags=tags,
        document_rows=doc_rows,
    )
    # Lazy import to avoid a module cycle (profile imports these dataclasses).
    from app.presentation.workspace_profile import resolve_profiled_packet

    packet = resolve_profiled_packet(
        db,
        ws,
        document_rows=doc_rows,
        heuristic=heuristic,
        user_id=user_id,
    )
    # Cached packets carry budgets computed at cache time — recompute from the
    # fresh evidence so an emptied/filled workspace gets the right limits.
    packet.derived.tool_policy = _tool_policy_for(
        len(packet.evidence.documents_ready),
        len(packet.evidence.documents_pending),
        packet.derived.tool_policy.external_context_ok,
    )
    return packet


def format_workspace_context_for_agent(packet: WorkspaceContextPacket) -> str:
    """Human-readable block injected into the main agent prompt."""
    d = packet.derived
    e = packet.evidence
    i = packet.identity
    policy = d.tool_policy

    ready_line = ", ".join(e.documents_ready[:8]) if e.documents_ready else "(none ready)"
    pending_line = (
        ", ".join(e.documents_pending[:6]) if e.documents_pending else "(none)"
    )
    tags_line = ", ".join(i.tags) if i.tags else "(none)"
    sections = ", ".join(d.answer_sections) if d.answer_sections else "(flexible)"
    afford = ", ".join(d.visual_affordances) if d.visual_affordances else "(generic)"

    web_rule = (
        f"web_search allowed (at most {policy.max_web_search} call(s)); "
        f"fetch_url allowed (at most {policy.max_fetch_url} page fetch(es)); "
        "prefer workspace documents first; label web-sourced general knowledge."
        if policy.external_context_ok
        else (
            "web_search and fetch_url are OFF for this workspace — "
            "use workspace documents only."
        )
    )

    research_block = ""
    if not e.documents_ready and policy.external_context_ok:
        research_block = (
            "- RESEARCH MODE: this workspace has no ready documents. Do NOT answer "
            "'no documents found'. Research the goal directly: web_search for the "
            "topic, then fetch_url on the most relevant results — and if the user's "
            "goal contains a URL, fetch that first. Label the answer as web-sourced.\n"
        )

    desc = i.description or (
        "(no description — treat as a generic document workspace; "
        "suggest the user add a description for better framing)"
    )

    domain_line = f"- Domain: {d.domain_label}\n" if d.domain_label else ""
    return (
        "WORKSPACE CONTEXT (derived — follow this framing):\n"
        f"- Name: {i.name or '(unnamed)'}\n"
        f"{domain_line}"
        f"- Description: {desc}\n"
        f"- Tags: {tags_line}\n"
        f"- Outcome: {d.outcome_phrase}\n"
        f"- Audience: {d.audience_phrase}\n"
        f"- Success looks like: {d.success_criteria}\n"
        f"- Tone: {d.tone}\n"
        f"- Suggested answer sections: {sections}\n"
        f"- Visual affordances (for later presentation only — do NOT describe UI): {afford}\n"
        f"- Documents ready ({len(e.documents_ready)}): {ready_line}\n"
        f"- Documents pending ({len(e.documents_pending)}): {pending_line}\n"
        f"- Filename hints: {', '.join(e.filename_hints[:12]) or '(none)'}\n"
        f"- Tool policy: at most {policy.max_search_documents} search_documents "
        f"call(s); {web_rule}\n"
        f"{research_block}"
        f"- Confidence: {packet.meta.confidence} "
        f"(derivation v{packet.meta.derivation_version})\n"
        "The user goal below is a task *inside* this workspace — not a redefinition of it."
    )


def format_main_agent_system_prompt(base_prompt: str, packet: WorkspaceContextPacket) -> str:
    """Compose fixed agent template + derived workspace packet."""
    return f"{base_prompt.rstrip()}\n\n{format_workspace_context_for_agent(packet)}"


def format_workspace_block_for_handoff(packet: WorkspaceContextPacket) -> str:
    """Compact workspace signal for handoff extraction."""
    d = packet.derived
    i = packet.identity
    return (
        f"Workspace: {i.name or '(unnamed)'}\n"
        f"Description: {(i.description or '')[:400] or '(none)'}\n"
        f"Outcome: {d.outcome_phrase}\n"
        f"Tone: {d.tone}\n"
        f"Success: {d.success_criteria}\n"
        f"Suggested affordances: {', '.join(d.visual_affordances[:10])}"
    )
