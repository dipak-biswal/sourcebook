"""Workspace Curator agent (agentic RAG over user-supplied URLs only).

Pipeline:
  1. Validate + fetch each user URL (fetch_url tool — no open web search).
  2. LLM: write workspace description from fetched text only.
  3. LLM: structure hierarchical curriculum with per-topic source_urls for citation.

This is intentionally separate from the Agents page run loop.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agents.main.tools.fetch_url import fetch_url_content, validate_fetch_url
from app.config import settings
from app.curriculum.discover import _flatten_chapters
from app.prompts.workspace_curator import (
    WORKSPACE_CURATOR_CURRICULUM_SYSTEM,
    WORKSPACE_CURATOR_DESCRIPTION_SYSTEM,
)
from app.usage import estimate_tokens, log_usage

_MAX_URLS = 12
_CHARS_PER_SOURCE = 6000

_DESC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "tags"],
    "additionalProperties": False,
}

_CHILD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "source_urls": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "tags", "source_urls"],
    "additionalProperties": False,
}

_CURRICULUM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                    "children": {
                        "type": "array",
                        "items": _CHILD_SCHEMA,
                    },
                },
                "required": ["title", "summary", "tags", "source_urls", "children"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["chapters"],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_urls(urls: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls or []:
        u = str(raw or "").strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        key = u.rstrip("/")
        if key in seen:
            continue
        err = validate_fetch_url(u)
        if err:
            continue
        seen.add(key)
        out.append(u)
        if len(out) >= _MAX_URLS:
            break
    return out


def _fetch_sources(
    urls: list[str],
    *,
    db: Session | None,
    user_id: Any,
    workspace_id: Any,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for u in urls:
        payload = fetch_url_content(u, max_chars=_CHARS_PER_SOURCE)
        entry: dict[str, Any] = {
            "url": u,
            "final_url": str(payload.get("final_url") or u),
            "title": str(payload.get("title") or "").strip()[:300],
            "text": str(payload.get("text") or "")[:_CHARS_PER_SOURCE],
            "error": payload.get("error"),
            "status_code": payload.get("status_code"),
            "fetched_at": _now_iso(),
        }
        sources.append(entry)
        if db is not None and user_id is not None:
            try:
                log_usage(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    kind="workspace_curator_fetch",
                    tool_name="fetch_url",
                    tool_input={"url": u},
                    tool_output={
                        "title": entry["title"],
                        "error": entry.get("error"),
                        "chars": len(entry.get("text") or ""),
                    },
                    meta={"call_type": "tool", "agent": "workspace_curator"},
                )
            except Exception:
                pass
    return sources


def _sources_prompt_block(sources: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, s in enumerate(sources, start=1):
        url = s.get("url") or ""
        title = s.get("title") or "(no title)"
        err = s.get("error")
        text = (s.get("text") or "").strip()
        if err:
            parts.append(f"### Source [{i}] {url}\nFETCH ERROR: {err}\n")
        else:
            parts.append(
                f"### Source [{i}] {title}\nURL: {url}\n\n{text[:_CHARS_PER_SOURCE]}\n"
            )
    return "\n".join(parts) if parts else "(no source text)"


def _llm_description(
    name: str,
    sources: list[dict[str, Any]],
    *,
    db: Session | None,
    user_id: Any,
    workspace_id: Any,
) -> tuple[str, list[str]]:
    ok_sources = [s for s in sources if not s.get("error") and (s.get("text") or "").strip()]
    fallback_desc = (
        f"Learning workspace for {name}. "
        + (
            f"Curriculum is drawn from {len(ok_sources)} user-supplied source(s)."
            if ok_sources
            else "Add public documentation URLs to build a grounded topic catalog."
        )
    )
    tags = ["learning"]
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if slug:
        tags.append(slug[:40])

    if not ok_sources:
        return fallback_desc, tags

    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    block = _sources_prompt_block(ok_sources)
    user_prompt = (
        f"Workspace name: {name}\n\n"
        f"Fetched sources (ONLY these):\n{block}\n\n"
        "Write description + tags grounded in the sources above."
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=WORKSPACE_CURATOR_DESCRIPTION_SYSTEM,
            prompt=user_prompt,
            schema_name="workspace_curator_description",
            schema=_DESC_SCHEMA,
            temperature=0.15,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            d = str(parsed.get("description") or "").strip()
            if d:
                fallback_desc = d[:2000]
            tlist = parsed.get("tags")
            if isinstance(tlist, list) and tlist:
                tags = [str(x).strip() for x in tlist if str(x).strip()][:6]
                if "learning" not in {x.lower() for x in tags}:
                    tags = ["learning", *tags][:6]
        if db is not None and user_id is not None:
            usage = getattr(resp, "usage", None)
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            if pt == 0 and ct == 0:
                pt = estimate_tokens(user_prompt)
                ct = estimate_tokens(raw)
            try:
                log_usage(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    kind="workspace_curator_description",
                    model=model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=pt + ct,
                    prompt=user_prompt,
                    completion=raw,
                    meta={"call_type": "llm", "agent": "workspace_curator"},
                )
            except Exception:
                pass
    except Exception:
        pass
    return fallback_desc, tags


def _attach_source_urls_to_topics(
    topics: list[dict[str, Any]],
    chapters_raw: list[dict[str, Any]],
    allowed_urls: set[str],
) -> list[dict[str, Any]]:
    """Map chapter tree source_urls onto flattened topics by title match."""
    by_title: dict[str, list[str]] = {}
    for ch in chapters_raw:
        if not isinstance(ch, dict):
            continue
        t = str(ch.get("title") or "").strip().lower()
        urls = [
            str(u).strip()
            for u in (ch.get("source_urls") or [])
            if str(u).strip() in allowed_urls or str(u).strip().rstrip("/") in {
                a.rstrip("/") for a in allowed_urls
            }
        ]
        if not urls:
            urls = list(allowed_urls)[:3]
        if t:
            by_title[t] = urls[:6]
        for child in ch.get("children") or []:
            if not isinstance(child, dict):
                continue
            ct = str(child.get("title") or "").strip().lower()
            curls = [
                str(u).strip()
                for u in (child.get("source_urls") or [])
                if str(u).strip()
            ]
            # Keep only allowed URLs (or parent urls)
            curls = [u for u in curls if u in allowed_urls or u.rstrip("/") in {
                a.rstrip("/") for a in allowed_urls
            }] or urls
            if ct:
                by_title[ct] = curls[:6]

    out: list[dict[str, Any]] = []
    for topic in topics:
        t = dict(topic)
        key = str(t.get("title") or "").strip().lower()
        src = by_title.get(key) or list(allowed_urls)[:3]
        t["source_urls"] = src
        out.append(t)
    return out


def _llm_curriculum(
    name: str,
    sources: list[dict[str, Any]],
    *,
    db: Session | None,
    user_id: Any,
    workspace_id: Any,
) -> list[dict[str, Any]]:
    ok_sources = [s for s in sources if not s.get("error") and (s.get("text") or "").strip()]
    if not ok_sources:
        return []

    allowed = {str(s.get("url") or "") for s in ok_sources if s.get("url")}
    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    block = _sources_prompt_block(ok_sources)
    user_prompt = (
        f"Workspace / subject: {name}\n\n"
        f"Allowed source URLs (use only these in source_urls fields):\n"
        + "\n".join(f"- {u}" for u in sorted(allowed))
        + f"\n\nFetched content:\n{block}\n\n"
        "Build a hierarchical curriculum that a learner should cover, ordered "
        "systematically from foundations to advanced, using only this material."
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=WORKSPACE_CURATOR_CURRICULUM_SYSTEM,
            prompt=user_prompt,
            schema_name="workspace_curator_curriculum",
            schema=_CURRICULUM_SCHEMA,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return []
        chapters = parsed.get("chapters") or []
        if not isinstance(chapters, list) or len(chapters) < 1:
            return []
        topics = _flatten_chapters(chapters, source="suggested")
        topics = _attach_source_urls_to_topics(topics, chapters, allowed)
        if db is not None and user_id is not None:
            usage = getattr(resp, "usage", None)
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            if pt == 0 and ct == 0:
                pt = estimate_tokens(user_prompt)
                ct = estimate_tokens(raw)
            try:
                log_usage(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    kind="workspace_curator_curriculum",
                    model=model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=pt + ct,
                    prompt=user_prompt,
                    completion=raw,
                    meta={
                        "call_type": "llm",
                        "agent": "workspace_curator",
                        "topic_count": len(topics),
                        "source_count": len(ok_sources),
                    },
                )
            except Exception:
                pass
        return topics
    except Exception:
        return []


def curate_from_urls(
    *,
    name: str,
    urls: list[str],
    db: Session | None = None,
    user_id: Any = None,
    workspace_id: Any = None,
) -> dict[str, Any]:
    """
    Run the Workspace Curator agent.

    Returns description, tags, sources (fetch audit), and flattened topics
    with source_urls for later Learn-page citation.
    """
    n = (name or "").strip() or "Learning"
    clean_urls = _normalize_urls(urls)
    sources = _fetch_sources(
        clean_urls, db=db, user_id=user_id, workspace_id=workspace_id
    )
    description, tags = _llm_description(
        n, sources, db=db, user_id=user_id, workspace_id=workspace_id
    )
    topics = _llm_curriculum(
        n, sources, db=db, user_id=user_id, workspace_id=workspace_id
    )

    # Public source records (no full text dump in API response by default)
    public_sources = [
        {
            "url": s.get("url"),
            "final_url": s.get("final_url"),
            "title": s.get("title") or "",
            "error": s.get("error"),
            "status_code": s.get("status_code"),
            "fetched_at": s.get("fetched_at"),
            "ok": not bool(s.get("error")) and bool((s.get("text") or "").strip()),
            "chars": len(s.get("text") or ""),
        }
        for s in sources
    ]

    return {
        "name": n,
        "description": description,
        "tags": tags,
        "sources": public_sources,
        "source_urls": [s["url"] for s in public_sources if s.get("url")],
        "topics": topics,
        "ok_source_count": sum(1 for s in public_sources if s.get("ok")),
        "fetched_at": _now_iso(),
        "agent": "workspace_curator",
    }
