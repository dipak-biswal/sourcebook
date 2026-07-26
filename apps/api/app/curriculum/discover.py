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

# Cheap fallbacks when web/LLM unavailable — keyed by domain keyword signals.
_FALLBACK_BY_SIGNAL: list[tuple[re.Pattern[str], list[dict[str, str]]]] = [
    (
        re.compile(r"system\s*design|distributed|scalability", re.I),
        [
            {"title": "Load balancer", "summary": "Distribute traffic across servers.", "tags": "networking,scalability"},
            {"title": "Caching", "summary": "Speed reads with Redis/CDN and invalidation.", "tags": "performance"},
            {"title": "Database sharding", "summary": "Split data for scale and locality.", "tags": "data"},
            {"title": "Consistent hashing", "summary": "Stable key→node mapping under churn.", "tags": "data"},
            {"title": "Message queues", "summary": "Async work via Kafka/RabbitMQ/SQS.", "tags": "messaging"},
            {"title": "Outbox pattern", "summary": "Reliable dual-write of DB + events.", "tags": "messaging,reliability"},
            {"title": "CAP theorem", "summary": "Consistency vs availability tradeoffs.", "tags": "theory"},
            {"title": "Rate limiting", "summary": "Protect APIs with token/leaky bucket.", "tags": "networking"},
            {"title": "CDN & edge", "summary": "Serve static and edge compute closer to users.", "tags": "networking"},
            {"title": "Microservices vs monolith", "summary": "When to split services and the costs.", "tags": "architecture"},
            {"title": "Idempotency", "summary": "Safe retries for at-least-once delivery.", "tags": "reliability"},
            {"title": "Observability", "summary": "Logs, metrics, traces for production systems.", "tags": "ops"},
        ],
    ),
    (
        re.compile(r"\b(dsa|algorithm|data\s*structure|leetcode)\b", re.I),
        [
            {"title": "Arrays & two pointers", "summary": "Linear scans and pair problems.", "tags": "arrays"},
            {"title": "Hash maps", "summary": "O(1) lookup patterns and frequency maps.", "tags": "hashing"},
            {"title": "Binary search", "summary": "Search on sorted ranges and answer spaces.", "tags": "search"},
            {"title": "Linked lists", "summary": "Pointer rewiring and cycle detection.", "tags": "lists"},
            {"title": "Stacks & queues", "summary": "LIFO/FIFO patterns and monotonic stacks.", "tags": "stacks"},
            {"title": "Trees & BST", "summary": "Traversals, insert/delete, balanced trees.", "tags": "trees"},
            {"title": "Graphs BFS/DFS", "summary": "Traversal, components, shortest paths intro.", "tags": "graphs"},
            {"title": "Heaps", "summary": "Priority queues and top-k patterns.", "tags": "heaps"},
            {"title": "Dynamic programming", "summary": "Optimal substructure and memoization.", "tags": "dp"},
            {"title": "Sliding window", "summary": "Subarray/substring constraints efficiently.", "tags": "arrays"},
        ],
    ),
]

_GENERIC_FALLBACK = [
    {"title": "Core concepts", "summary": "Foundational ideas for this workspace.", "tags": "basics"},
    {"title": "How it works", "summary": "End-to-end flow and main components.", "tags": "overview"},
    {"title": "Key tradeoffs", "summary": "When to choose which approach.", "tags": "tradeoffs"},
    {"title": "Common pitfalls", "summary": "Mistakes and how to avoid them.", "tags": "practice"},
    {"title": "Best practices", "summary": "Patterns that hold up in real systems.", "tags": "practice"},
    {"title": "Worked example", "summary": "Walk through a concrete scenario.", "tags": "example"},
]

_TOPIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain_label": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "summary", "tags"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["domain_label", "topics"],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _fallback_topics(domain: str) -> list[dict[str, Any]]:
    for pattern, rows in _FALLBACK_BY_SIGNAL:
        if pattern.search(domain):
            return _rows_to_topics(rows, source="fallback")
    return _rows_to_topics(_GENERIC_FALLBACK, source="fallback")


def _rows_to_topics(
    rows: list[dict[str, str]], *, source: str = "suggested"
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        tags = [t.strip() for t in str(row.get("tags") or "").split(",") if t.strip()]
        t = normalize_topic(
            {
                "id": slugify(row["title"]),
                "title": row["title"],
                "summary": row.get("summary") or "",
                "tags": tags,
                "source": source if source in ("suggested", "custom") else "suggested",
                "status": "active",
                "preferences": {},
            }
        )
        if t:
            out.append(t)
    return out


def _web_snippets(domain: str) -> list[str]:
    try:
        from app.agents.main.tools.web_search import search_web

        payload = search_web(
            f"{domain} core topics concepts for interviews study guide",
            max_results=6,
        )
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("error"):
        return []
    snippets: list[str] = []
    for r in payload.get("results") or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        snip = str(r.get("snippet") or "").strip()
        line = f"{title}: {snip}".strip(": ")
        if line:
            snippets.append(line[:300])
    return snippets[:8]


def _llm_topics(
    domain: str,
    snippets: list[str],
    *,
    db: Session | None,
    user_id: Any,
    workspace_id: Any,
) -> list[dict[str, Any]] | None:
    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    prompt = (
        f"Domain / workspace: {domain}\n\n"
        "Web context (may be noisy):\n"
        + ("\n".join(f"- {s}" for s in snippets) if snippets else "(none)")
        + "\n\n"
        "Return 12–16 distinct study topics for someone learning this domain. "
        "Titles short (2–5 words). Summaries one sentence. tags 1–3 short labels. "
        "No duplicates. Prefer interview/practical relevance."
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=(
                "You curate a learning topic catalog. Output only the JSON schema. "
                "Topics must be relevant to the given domain."
            ),
            prompt=prompt,
            schema_name="curriculum_topics",
            schema=_TOPIC_SCHEMA,
            temperature=0.2,
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
    topics: list[dict[str, Any]] = []
    for item in parsed.get("topics") or []:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        t = normalize_topic(
            {
                "title": item.get("title"),
                "summary": item.get("summary"),
                "tags": tags,
                "source": "suggested",
                "status": "active",
                "preferences": {},
            }
        )
        if t:
            topics.append(t)
    if len(topics) < 4:
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
                meta={"domain": domain[:120], "topic_count": len(topics)},
            )
        except Exception:
            pass
    return topics[:20]


def discover_topics(
    workspace: Workspace,
    *,
    db: Session,
    user_id: Any = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Return curriculum with topics, refreshing when fingerprint changes or force=True.
    Preserves custom topics and preferences on matching ids.
    """
    domain = domain_label(
        name=workspace.name or "",
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
    )
    fp = fingerprint_for(
        name=workspace.name or "",
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
    )
    existing = get_curriculum(workspace)
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

    snippets = _web_snippets(domain)
    topics = _llm_topics(
        domain,
        snippets,
        db=db,
        user_id=user_id,
        workspace_id=workspace.id,
    )
    source = "web+llm" if topics else "fallback"
    if not topics:
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
    }
    return save_curriculum(db, workspace, curriculum)
