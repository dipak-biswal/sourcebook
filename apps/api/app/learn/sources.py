"""Web + documentation sources for Learn catalog and setup helpers.

Prefer real web search / URL fetch over inventing topic trees.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.prompts.learn import LEARN_SUGGEST_SETUP_SYSTEM
from app.usage import estimate_tokens, log_usage

_YEAR = datetime.now(timezone.utc).year

_SUGGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "suggested_docs_url": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "suggested_docs_url", "tags"],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def web_search_snippets(
    query: str,
    *,
    max_results: int = 8,
) -> list[dict[str, str]]:
    """Latest web results as {title, url, snippet}."""
    try:
        from app.agents.main.tools.web_search import search_web

        payload = search_web(
            query,
            max_results=max_results,
            current_year=_YEAR,
        )
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("error"):
        return []
    out: list[dict[str, str]] = []
    for r in payload.get("results") or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        url = str(r.get("url") or "").strip()
        snip = str(r.get("snippet") or "").strip()
        if title or snip:
            out.append(
                {
                    "title": title[:200],
                    "url": url[:500],
                    "snippet": snip[:400],
                }
            )
    return out[:max_results]


def fetch_docs_text(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    """Fetch documentation page text (safe public URLs only)."""
    from app.agents.main.tools.fetch_url import fetch_url_content, validate_fetch_url

    err = validate_fetch_url(url)
    if err:
        return {"url": url, "error": err, "text": "", "title": ""}
    try:
        payload = fetch_url_content(url, max_chars=max_chars)
    except Exception as exc:
        return {"url": url, "error": str(exc), "text": "", "title": ""}
    if not isinstance(payload, dict):
        return {"url": url, "error": "invalid fetch payload", "text": "", "title": ""}
    if payload.get("error"):
        return {
            "url": url,
            "error": str(payload.get("error")),
            "text": "",
            "title": "",
        }
    return {
        "url": str(payload.get("final_url") or payload.get("url") or url),
        "title": str(payload.get("title") or "")[:300],
        "text": str(payload.get("text") or "")[:max_chars],
        "error": None,
    }


def suggest_from_name(
    name: str,
    *,
    db: Session | None = None,
    user_id: Any = None,
    workspace_id: Any = None,
) -> dict[str, Any]:
    """
    Suggest workspace description + optional docs URL from the name via web search.
    """
    n = (name or "").strip()
    if not n:
        return {
            "description": "",
            "suggested_docs_url": "",
            "tags": ["learning"],
            "snippets": [],
        }

    queries = [
        f"{n} official documentation site {_YEAR}",
        f"{n} programming language OR framework overview documentation table of contents",
        f"what is {n} learn tutorial topics {_YEAR}",
    ]
    snippets: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for q in queries:
        for row in web_search_snippets(q, max_results=5):
            u = row.get("url") or ""
            if u and u in seen_urls:
                continue
            if u:
                seen_urls.add(u)
            snippets.append(row)
        if len(snippets) >= 10:
            break

    # Prefer official-looking docs URLs from search.
    suggested_url = ""
    for row in snippets:
        u = (row.get("url") or "").lower()
        if any(
            k in u
            for k in (
                "docs.",
                "/docs",
                "documentation",
                "readthedocs",
                "developer.",
                "dev.",
                "wiki.python",
                "docs.python",
            )
        ):
            suggested_url = row.get("url") or ""
            break
    if not suggested_url and snippets:
        suggested_url = snippets[0].get("url") or ""

    context = "\n".join(
        f"- {s.get('title')}: {s.get('snippet')} ({s.get('url')})"
        for s in snippets[:8]
    )
    description = (
        f"Learning workspace for {n}. Explore core concepts, APIs, and practical "
        f"patterns using current documentation and web sources ({_YEAR})."
    )
    tags = ["learning"]
    # Light tag from name
    slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
    if slug and slug not in tags:
        tags.append(slug[:40])

    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=LEARN_SUGGEST_SETUP_SYSTEM,
            prompt=(
                f"Workspace name: {n}\n"
                f"Year: {_YEAR}\n"
                f"Web search results:\n{context or '(none)'}\n\n"
                f"Suggested docs URL candidate: {suggested_url or '(none)'}"
            ),
            schema_name="learn_suggest_setup",
            schema=_SUGGEST_SCHEMA,
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            d = str(parsed.get("description") or "").strip()
            if d:
                description = d[:2000]
            u = str(parsed.get("suggested_docs_url") or "").strip()
            if u.startswith("http"):
                suggested_url = u[:2000]
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
                pt = estimate_tokens(context)
                ct = estimate_tokens(raw)
            try:
                log_usage(
                    db,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    kind="learn_suggest",
                    model=model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=pt + ct,
                    prompt=(
                        f"Workspace name: {n}\nWeb search results:\n{context or '(none)'}"
                    ),
                    completion=raw,
                    meta={
                        "name": n[:80],
                        "call_type": "llm",
                        "web_hits": len(snippets),
                    },
                )
            except Exception:
                pass
    except Exception:
        pass

    # Record web search activity for workspace audit (even without LLM).
    if db is not None and user_id is not None and snippets:
        try:
            log_usage(
                db,
                user_id=user_id,
                workspace_id=workspace_id,
                kind="web_search",
                model=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                tool_name="web_search",
                tool_input={"queries": [f"{n} official documentation", f"what is {n}"]},
                tool_output={"results": snippets[:6]},
                meta={"name": n[:80], "call_type": "web_search", "result_count": len(snippets)},
            )
        except Exception:
            pass

    return {
        "description": description,
        "suggested_docs_url": suggested_url,
        "tags": tags,
        "snippets": snippets[:8],
    }


def gather_source_context(
    *,
    domain: str,
    name: str = "",
    docs_url: str | None = None,
    docs_only: bool = False,
) -> dict[str, Any]:
    """
    Collect source text for topic extraction.

    When docs_only=True and docs_url is set, only fetch that documentation
    page (plus optional same-host TOC search). Otherwise also run broad web search.
    """
    label = (domain or name or "learning").strip()
    year = _YEAR
    snippets: list[dict[str, str]] = []

    docs: dict[str, Any] = {"url": "", "text": "", "title": "", "error": None}
    url = (docs_url or "").strip()
    if url:
        docs = fetch_docs_text(url, max_chars=14000)
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""
        if host:
            # Stay on the docs site only when building a docs-driven catalog.
            snippets.extend(
                web_search_snippets(
                    f"site:{host} table of contents index tutorial {label} {year}",
                    max_results=6 if docs_only else 5,
                )
            )

    if not docs_only:
        search_queries = [
            f"{label} official documentation topics table of contents {year}",
            f"{label} documentation index tutorial chapters {year}",
            f"{label} language OR framework core topics API reference {year}",
        ]
        for q in search_queries:
            snippets.extend(web_search_snippets(q, max_results=6))
            if len(snippets) >= 12:
                break

    # Deduplicate snippets by url
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for s in snippets:
        key = s.get("url") or s.get("title") or ""
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    return {
        "domain": label,
        "year": year,
        "docs": docs,
        "snippets": uniq[:14],
        "docs_only": docs_only,
    }


def format_source_context_for_prompt(ctx: dict[str, Any]) -> str:
    lines = [
        f"Domain: {ctx.get('domain')}",
        f"Year: {ctx.get('year')}",
        "",
        "Latest web search results:",
    ]
    for s in ctx.get("snippets") or []:
        if not isinstance(s, dict):
            continue
        lines.append(
            f"- {s.get('title')}: {s.get('snippet')} ({s.get('url')})"
        )
    docs = ctx.get("docs") if isinstance(ctx.get("docs"), dict) else {}
    lines.append("")
    if docs.get("url"):
        lines.append(f"Documentation URL: {docs.get('url')}")
        if docs.get("title"):
            lines.append(f"Page title: {docs.get('title')}")
        if docs.get("error"):
            lines.append(f"Fetch error: {docs.get('error')}")
        text = str(docs.get("text") or "").strip()
        if text:
            lines.append("Documentation page text (excerpt):")
            lines.append(text[:10000])
        else:
            lines.append("(No page body — rely on web search results.)")
    else:
        lines.append("No documentation URL provided — use web search only.")
    return "\n".join(lines)
