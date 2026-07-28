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
        "Return a hierarchical learning catalog: 4–7 CHAPTERS (main topics). "
        "Each chapter has 3–5 CHILD lessons nested under it.\n"
        "Example shape: Scalability principles → Load balancer, Caching, CDN…\n"
        "Chapter titles: principle/area names (2–5 words). "
        "Child titles: concrete techniques or concepts. "
        "Summaries one sentence. tags 1–3 short labels. "
        "No duplicates across the tree. Prefer interview/practical relevance."
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=(
                "You curate a hierarchical learning catalog (chapters + nested "
                "lessons). Output only the JSON schema. Relevant to the domain."
            ),
            prompt=prompt,
            schema_name="curriculum_chapters",
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
    chapters = parsed.get("chapters") or []
    if not isinstance(chapters, list) or len(chapters) < 2:
        return None
    topics = _flatten_chapters(chapters, source="suggested")
    # Need at least a few chapters with some children.
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
                meta={
                    "domain": domain[:120],
                    "topic_count": len(topics),
                    "chapter_count": len(parents),
                },
            )
        except Exception:
            pass
    return topics[:60]


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
    }
    return save_curriculum(db, workspace, curriculum)
