"""Validate user-entered topics against workspace domain (polite decline if off-topic)."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.curriculum.domain import domain_label
from app.curriculum.schema import normalize_topic, slugify
from app.usage import estimate_tokens, log_usage

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "related": {"type": "boolean"},
        "reason": {"type": "string"},
        "normalized_title": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["related", "reason", "normalized_title", "summary"],
    "additionalProperties": False,
}


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


_OFF_TOPIC = re.compile(
    r"\b("
    r"recipe|cooking|cake|baking|football|soccer|dating|lottery|"
    r"gardening|fashion|makeup|celebrity|horoscope"
    r")\b",
    re.I,
)

_TECH_DOMAIN = re.compile(
    r"system|design|distributed|cache|queue|api|database|algorithm|"
    r"graph|tree|network|scale|interview|software|backend|frontend",
    re.I,
)

_TECH_TITLE = re.compile(
    r"\b("
    r"cache|hash|queue|shard|load|balance|api|database|sql|nosql|"
    r"consistent|cap|raft|paxos|kafka|redis|cdn|latency|throughput|"
    r"microservice|monolith|idempoten|observab|rate\s*limit|outbox|"
    r"binary|tree|graph|heap|sort|dp|pointer|array|list"
    r")\b",
    re.I,
)


def _heuristic_related(title: str, domain: str) -> bool:
    """Loose lexical overlap when LLM is unavailable."""
    if not (title or "").strip():
        return False
    if _OFF_TOPIC.search(title):
        return False
    t_words = set(re.findall(r"[a-z0-9]{3,}", title.lower()))
    d_words = set(re.findall(r"[a-z0-9]{3,}", domain.lower()))
    if t_words & d_words:
        return True
    # Technical domain: accept titles that look like CS/system-design terms.
    if _TECH_DOMAIN.search(domain or "") and _TECH_TITLE.search(title):
        return True
    return False


def validate_custom_topic(
    *,
    title: str,
    workspace_name: str,
    workspace_description: str | None,
    workspace_tags: list[str] | None,
    db: Session | None = None,
    user_id: Any = None,
    workspace_id: Any = None,
) -> dict[str, Any]:
    """
    Returns either:
      {"ok": True, "topic": {...}}
      {"ok": False, "code": "off_topic", "message": "..."}
    """
    title = (title or "").strip()
    if len(title) < 2:
        return {
            "ok": False,
            "code": "invalid",
            "message": "Please enter a topic name (at least 2 characters).",
        }
    if len(title) > 120:
        return {
            "ok": False,
            "code": "invalid",
            "message": "Topic name is too long (max 120 characters).",
        }

    domain = domain_label(
        name=workspace_name,
        description=workspace_description,
        tags=workspace_tags,
    )

    related: bool | None = None
    reason = ""
    normalized = title
    summary = ""

    model = getattr(settings, "context_agent_model", None) or settings.chat_model
    prompt = (
        f"Workspace domain: {domain}\n"
        f"Workspace description: {(workspace_description or '')[:400]}\n"
        f"Candidate topic: {title}\n\n"
        "Is this candidate a reasonable study topic for this workspace? "
        "Reject hobbies or unrelated subjects politely."
    )
    try:
        from app.agents.visual_summary.llm_json import chat_json

        resp = chat_json(
            _client(),
            model=model,
            system=(
                "You gate custom learning topics. Set related=true only when the "
                "topic fits the workspace domain. Write a short polite reason when false."
            ),
            prompt=prompt,
            schema_name="curriculum_validate_topic",
            schema=_SCHEMA,
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            related = bool(parsed.get("related"))
            reason = str(parsed.get("reason") or "").strip()
            normalized = str(parsed.get("normalized_title") or title).strip() or title
            summary = str(parsed.get("summary") or "").strip()
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
                        kind="curriculum_validate",
                        model=model,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        total_tokens=pt + ct,
                        meta={"related": related, "title": title[:80]},
                    )
                except Exception:
                    pass
    except Exception:
        related = _heuristic_related(title, domain)
        reason = (
            f"That doesn't look related to this workspace ({domain}). "
            "Try a topic that matches what you're learning here."
            if not related
            else "Looks related."
        )
        summary = f"Custom topic: {title}" if related else ""

    if related is False:
        msg = reason or (
            f"That doesn't look related to this workspace ({domain}). "
            "Try something closer to the workspace theme."
        )
        return {"ok": False, "code": "off_topic", "message": msg}

    topic = normalize_topic(
        {
            "id": slugify(normalized),
            "title": normalized[:120],
            "summary": (summary or f"Custom topic for {domain}.")[:400],
            "tags": ["custom"],
            "source": "custom",
            "status": "active",
            "preferences": {},
        }
    )
    if not topic:
        return {
            "ok": False,
            "code": "invalid",
            "message": "Could not save that topic. Try a different name.",
        }
    return {"ok": True, "topic": topic}
