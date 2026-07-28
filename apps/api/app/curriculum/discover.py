"""Discover topic cards for a learning workspace (web + small LLM + fallbacks)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.curriculum.domain import domain_label
from app.curriculum.schema import normalize_topic, slugify
from app.curriculum.service import fingerprint_for, get_curriculum, save_curriculum
from app.models import Workspace
from app.usage import estimate_tokens, log_usage

# Hierarchical fallbacks: chapters with nested child lessons.
# Each chapter becomes a parent topic (Introduction); children nest under it.
_FALLBACK_CHAPTERS_BY_SIGNAL: list[tuple[re.Pattern[str], list[dict[str, Any]]]] = [
    (
        re.compile(r"system\s*design|distributed|scalability", re.I),
        [
            {
                "title": "Scalability principles",
                "summary": "How systems grow with load: axes, bottlenecks, and levers.",
                "tags": ["scalability"],
                "children": [
                    {"title": "Load balancer", "summary": "Distribute traffic across servers.", "tags": ["networking"]},
                    {"title": "Caching", "summary": "Speed reads with Redis/CDN and invalidation.", "tags": ["performance"]},
                    {"title": "CDN & edge", "summary": "Serve content closer to users.", "tags": ["networking"]},
                    {"title": "Rate limiting", "summary": "Protect APIs with token/leaky bucket.", "tags": ["networking"]},
                ],
            },
            {
                "title": "Data & storage",
                "summary": "Partitioning, hashing, and scaling stateful systems.",
                "tags": ["data"],
                "children": [
                    {"title": "Database sharding", "summary": "Split data for scale and locality.", "tags": ["data"]},
                    {"title": "Consistent hashing", "summary": "Stable key→node mapping under churn.", "tags": ["data"]},
                    {"title": "Replication", "summary": "Copies for availability and read scale.", "tags": ["data"]},
                ],
            },
            {
                "title": "Messaging & reliability",
                "summary": "Async pipelines and safe delivery guarantees.",
                "tags": ["messaging"],
                "children": [
                    {"title": "Message queues", "summary": "Async work via Kafka/RabbitMQ/SQS.", "tags": ["messaging"]},
                    {"title": "Outbox pattern", "summary": "Reliable dual-write of DB + events.", "tags": ["reliability"]},
                    {"title": "Idempotency", "summary": "Safe retries for at-least-once delivery.", "tags": ["reliability"]},
                ],
            },
            {
                "title": "Architecture tradeoffs",
                "summary": "Choosing structure under real constraints.",
                "tags": ["architecture"],
                "children": [
                    {"title": "CAP theorem", "summary": "Consistency vs availability tradeoffs.", "tags": ["theory"]},
                    {"title": "Microservices vs monolith", "summary": "When to split services and the costs.", "tags": ["architecture"]},
                    {"title": "Observability", "summary": "Logs, metrics, traces for production.", "tags": ["ops"]},
                ],
            },
        ],
    ),
    (
        re.compile(r"\b(machine\s*learning|ml|deep\s*learning|neural)\b", re.I),
        [
            {
                "title": "Learning foundations",
                "summary": "What models learn and how training works.",
                "tags": ["ml"],
                "children": [
                    {"title": "Supervised learning", "summary": "Labels, loss, and generalization.", "tags": ["basics"]},
                    {"title": "Gradient descent", "summary": "Stepping parameters to minimize loss.", "tags": ["optimization"]},
                    {"title": "Train/val/test split", "summary": "Honest evaluation and overfitting.", "tags": ["practice"]},
                ],
            },
            {
                "title": "Optimizers",
                "summary": "Algorithms that update parameters on a loss surface.",
                "tags": ["optimization"],
                "children": [
                    {"title": "SGD", "summary": "Stochastic steps with a fixed learning rate.", "tags": ["optimization"]},
                    {"title": "RMSprop", "summary": "Adaptive rates from squared gradients.", "tags": ["optimization"]},
                    {"title": "Adam", "summary": "Momentum plus adaptive second moments.", "tags": ["optimization"]},
                ],
            },
            {
                "title": "Neural networks",
                "summary": "Layers, activations, and backprop intuition.",
                "tags": ["deep-learning"],
                "children": [
                    {"title": "Forward pass", "summary": "Compute predictions through layers.", "tags": ["basics"]},
                    {"title": "Backpropagation", "summary": "Chain rule for gradients.", "tags": ["theory"]},
                    {"title": "Regularization", "summary": "Dropout, weight decay, early stop.", "tags": ["practice"]},
                ],
            },
        ],
    ),
    (
        re.compile(r"\b(dsa|algorithm|data\s*structure|leetcode)\b", re.I),
        [
            {
                "title": "Arrays & hashing",
                "summary": "Linear structures and O(1) lookup patterns.",
                "tags": ["arrays"],
                "children": [
                    {"title": "Arrays & two pointers", "summary": "Linear scans and pair problems.", "tags": ["arrays"]},
                    {"title": "Hash maps", "summary": "O(1) lookup and frequency maps.", "tags": ["hashing"]},
                    {"title": "Sliding window", "summary": "Subarray constraints efficiently.", "tags": ["arrays"]},
                ],
            },
            {
                "title": "Trees & graphs",
                "summary": "Hierarchical and networked structures.",
                "tags": ["graphs"],
                "children": [
                    {"title": "Trees & BST", "summary": "Traversals, insert/delete, balance.", "tags": ["trees"]},
                    {"title": "Graphs BFS/DFS", "summary": "Traversal, components, shortest paths.", "tags": ["graphs"]},
                    {"title": "Heaps", "summary": "Priority queues and top-k patterns.", "tags": ["heaps"]},
                ],
            },
            {
                "title": "Search & DP",
                "summary": "Binary search space and optimal substructure.",
                "tags": ["dp"],
                "children": [
                    {"title": "Binary search", "summary": "Search on sorted ranges and answers.", "tags": ["search"]},
                    {"title": "Dynamic programming", "summary": "Memoization and tabulation.", "tags": ["dp"]},
                    {"title": "Stacks & queues", "summary": "LIFO/FIFO and monotonic stacks.", "tags": ["stacks"]},
                ],
            },
        ],
    ),
]

_GENERIC_CHAPTERS: list[dict[str, Any]] = [
    {
        "title": "Core concepts",
        "summary": "Foundational ideas for this workspace.",
        "tags": ["basics"],
        "children": [
            {"title": "How it works", "summary": "End-to-end flow and main components.", "tags": ["overview"]},
            {"title": "Key tradeoffs", "summary": "When to choose which approach.", "tags": ["tradeoffs"]},
            {"title": "Common pitfalls", "summary": "Mistakes and how to avoid them.", "tags": ["practice"]},
        ],
    },
    {
        "title": "Practice",
        "summary": "Apply the ideas on concrete work.",
        "tags": ["practice"],
        "children": [
            {"title": "Best practices", "summary": "Patterns that hold up in real systems.", "tags": ["practice"]},
            {"title": "Worked example", "summary": "Walk through a concrete scenario.", "tags": ["example"]},
        ],
    },
]

_CHILD_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "tags"],
    "additionalProperties": False,
}

_TOPIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain_label": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "children": {
                        "type": "array",
                        "items": _CHILD_ITEM,
                    },
                },
                "required": ["title", "summary", "tags", "children"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["domain_label", "chapters"],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _tags_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()][:8]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()][:8]
    return []


def _flatten_chapters(
    chapters: list[dict[str, Any]],
    *,
    source: str = "suggested",
) -> list[dict[str, Any]]:
    """Expand chapter trees into flat topics with parent_id links."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        title = str(ch.get("title") or "").strip()
        if not title:
            continue
        parent = normalize_topic(
            {
                "id": slugify(title),
                "title": title,
                "summary": ch.get("summary") or "",
                "tags": _tags_list(ch.get("tags")),
                "source": source if source in ("suggested", "custom") else "suggested",
                "status": "active",
                "preferences": {},
                "parent_id": None,
                "kind": "chapter",
            }
        )
        if not parent or parent["id"] in seen:
            continue
        seen.add(parent["id"])
        out.append(parent)
        for child in ch.get("children") or []:
            if not isinstance(child, dict):
                continue
            ctitle = str(child.get("title") or "").strip()
            if not ctitle:
                continue
            cid = slugify(ctitle)
            if cid == parent["id"]:
                cid = f"{parent['id']}-{cid}"[:80]
            ct = normalize_topic(
                {
                    "id": cid,
                    "title": ctitle,
                    "summary": child.get("summary") or "",
                    "tags": _tags_list(child.get("tags")),
                    "source": source if source in ("suggested", "custom") else "suggested",
                    "status": "active",
                    "preferences": {},
                    "parent_id": parent["id"],
                    "kind": "lesson",
                }
            )
            if ct and ct["id"] not in seen:
                seen.add(ct["id"])
                out.append(ct)
    return out


def _fallback_topics(domain: str) -> list[dict[str, Any]]:
    for pattern, chapters in _FALLBACK_CHAPTERS_BY_SIGNAL:
        if pattern.search(domain):
            return _flatten_chapters(chapters, source="fallback")
    return _flatten_chapters(_GENERIC_CHAPTERS, source="fallback")


def _llm_topics_from_sources(
    domain: str,
    source_prompt: str,
    *,
    docs_url: str = "",
    db: Session | None,
    user_id: Any,
    workspace_id: Any,
) -> list[dict[str, Any]] | None:
    """Structure a hierarchical catalog from real web/docs evidence only."""
    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    prompt = (
        f"{source_prompt}\n\n"
        "Using ONLY the web search results and documentation text above "
        f"(year context included for latest info), build a hierarchical learning "
        "catalog for this domain.\n"
        "Rules:\n"
        "- 4–10 CHAPTERS (main sections of the subject / docs).\n"
        "- Each chapter has 3–8 CHILD lessons (real subtopics from the sources).\n"
        "- Prefer official documentation outline (e.g. Python docs: intro, "
        "data structures, modules, stdlib topics…).\n"
        "- Titles short (2–6 words). Summaries one sentence grounded in sources.\n"
        "- tags 1–3 short labels. No invented APIs that contradict the docs.\n"
        "- If a docs URL was provided, mirror its TOC structure when visible.\n"
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=(
                "You extract a hierarchical learning catalog from documentation "
                "and web search evidence. Do not invent topics unsupported by "
                "the sources. Output only the JSON schema."
            ),
            prompt=prompt,
            schema_name="curriculum_chapters",
            schema=_TOPIC_SCHEMA,
            temperature=0.15,
        )
    except Exception:
        return None
    raw = (resp.choices[0].message.content or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    chapters = parsed.get("chapters") or []
    if not isinstance(chapters, list) or len(chapters) < 2:
        return None
    topics = _flatten_chapters(chapters, source="suggested")
    parents = [t for t in topics if not t.get("parent_id")]
    children = [t for t in topics if t.get("parent_id")]
    if len(parents) < 2 or len(children) < 3:
        return None

    if db is not None and user_id is not None and workspace_id is not None:
        usage = getattr(resp, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0)
        ct = int(getattr(usage, "completion_tokens", 0) or 0)
        if pt == 0 and ct == 0:
            pt = estimate_tokens(prompt)
            ct = estimate_tokens(raw)
        try:
            log_usage(
                db,
                user_id=user_id,
                workspace_id=workspace_id,
                kind="curriculum_discover",
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=pt + ct,
                prompt=prompt,
                completion=raw,
                meta={
                    "domain": domain[:120],
                    "topic_count": len(topics),
                    "chapter_count": len(parents),
                    "docs_url": (docs_url or "")[:200],
                    "call_type": "llm",
                },
            )
        except Exception:
            pass
    return topics[:80]


def discover_topics(
    workspace: Workspace,
    *,
    db: Session,
    user_id: Any = None,
    force: bool = False,
    docs_url: str | None = None,
) -> dict[str, Any]:
    """
    Return curriculum with topics, refreshing when fingerprint changes or force=True.

    Always gathers latest web search results; when docs_url (or stored
    curriculum.docs_url) is set, also fetches that documentation page and
    structures chapters/subtopics from the evidence.
    """
    existing = get_curriculum(workspace)
    stored_docs = str(existing.get("docs_url") or "").strip()
    effective_docs = (docs_url if docs_url is not None else stored_docs).strip()

    domain = domain_label(
        name=workspace.name or "",
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
    )
    fp = fingerprint_for(
        name=workspace.name or "",
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
        docs_url=effective_docs or None,
    )
    if (
        not force
        and existing.get("topics")
        and existing.get("fingerprint") == fp
        and existing.get("source") not in ("empty", None, "")
    ):
        return existing

    # Preserve customs + prefs by id
    prev_by_id = {
        str(t["id"]): t
        for t in (existing.get("topics") or [])
        if isinstance(t, dict) and t.get("id")
    }

    from app.learn.sources import format_source_context_for_prompt, gather_source_context
    from app.usage import log_usage as _log_usage_activity

    ctx = gather_source_context(
        domain=domain or (workspace.name or "learning"),
        name=workspace.name or "",
        docs_url=effective_docs or None,
    )
    # Audit trail: web search + docs fetch for this workspace.
    try:
        if ctx.get("snippets") and user_id is not None:
            _log_usage_activity(
                db,
                user_id=user_id,
                workspace_id=workspace.id,
                kind="web_search",
                tool_name="web_search",
                tool_input={
                    "domain": domain,
                    "docs_url": effective_docs or None,
                },
                tool_output={"results": (ctx.get("snippets") or [])[:8]},
                meta={
                    "call_type": "web_search",
                    "result_count": len(ctx.get("snippets") or []),
                },
            )
        docs = ctx.get("docs") if isinstance(ctx.get("docs"), dict) else {}
        if effective_docs and user_id is not None:
            _log_usage_activity(
                db,
                user_id=user_id,
                workspace_id=workspace.id,
                kind="fetch_url",
                tool_name="fetch_url",
                tool_input={"url": effective_docs},
                tool_output={
                    "title": docs.get("title"),
                    "error": docs.get("error"),
                    "text_preview": str(docs.get("text") or "")[:2000],
                },
                meta={"call_type": "tool", "url": effective_docs[:200]},
            )
    except Exception:
        pass

    source_prompt = format_source_context_for_prompt(ctx)
    topics = _llm_topics_from_sources(
        domain,
        source_prompt,
        docs_url=effective_docs,
        db=db,
        user_id=user_id,
        workspace_id=workspace.id,
    )
    has_docs = bool(effective_docs) and not (ctx.get("docs") or {}).get("error")
    has_web = bool(ctx.get("snippets"))
    if topics and has_docs and has_web:
        source = "docs+web"
    elif topics and has_docs:
        source = "docs"
    elif topics and has_web:
        source = "web"
    elif topics:
        source = "web+llm"
    else:
        source = "fallback"
        topics = _fallback_topics(domain)

    # Merge: suggested list + any previous custom topics not in list
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in topics:
        tid = t["id"]
        prev = prev_by_id.get(tid)
        if prev:
            if prev.get("preferences"):
                t["preferences"] = prev["preferences"]
            if prev.get("source") == "custom":
                t["source"] = "custom"
            if prev.get("status") == "archived":
                t["status"] = "archived"
            # Keep prior hierarchy only if new topic omitted parent.
            if not t.get("parent_id") and prev.get("parent_id"):
                t["parent_id"] = prev["parent_id"]
                t["kind"] = prev.get("kind") or t.get("kind") or "lesson"
        merged.append(t)
        seen.add(tid)
    for tid, prev in prev_by_id.items():
        if tid not in seen and prev.get("source") == "custom":
            merged.append(prev)
            seen.add(tid)

    curriculum = {
        "version": 1,
        "domain": domain,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fingerprint": fp,
        "topics": merged,
        "last_selected_topic_id": existing.get("last_selected_topic_id"),
        "lessons": existing.get("lessons") if isinstance(existing.get("lessons"), dict) else {},
        "docs_url": effective_docs,
    }
    return save_curriculum(db, workspace, curriculum)
