"""Curriculum data shapes (dict-in/dict-out for JSON column storage)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

CURRICULUM_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").strip().lower())
    s = s.strip("-")
    return s[:80] or f"topic-{uuid.uuid4().hex[:8]}"


def empty_curriculum(*, domain: str = "") -> dict[str, Any]:
    return {
        "version": CURRICULUM_VERSION,
        "domain": (domain or "").strip(),
        "source": "empty",
        "fetched_at": None,
        "fingerprint": "",
        "topics": [],
        "last_selected_topic_id": None,
    }


def normalize_topic(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    if not title:
        return None
    tid = str(raw.get("id") or "").strip() or slugify(title)
    prefs = raw.get("preferences") if isinstance(raw.get("preferences"), dict) else {}
    # preferences: map of question_id → list[str] option ids
    clean_prefs: dict[str, list[str]] = {}
    for k, v in prefs.items():
        key = str(k).strip()
        if not key:
            continue
        if isinstance(v, list):
            clean_prefs[key] = [str(x).strip() for x in v if str(x).strip()]
        elif v is not None and str(v).strip():
            clean_prefs[key] = [str(v).strip()]
    status = str(raw.get("status") or "active").strip().lower()
    if status not in ("active", "archived"):
        status = "active"
    source = str(raw.get("source") or "suggested").strip().lower()
    if source not in ("suggested", "custom"):
        source = "suggested"
    tags_raw = raw.get("tags") or []
    tags = (
        [str(t).strip() for t in tags_raw if str(t).strip()][:8]
        if isinstance(tags_raw, list)
        else []
    )
    return {
        "id": tid[:80],
        "title": title[:120],
        "summary": str(raw.get("summary") or "").strip()[:400],
        "tags": tags,
        "source": source,
        "status": status,
        "preferences": clean_prefs,
        "updated_at": str(raw.get("updated_at") or _now_iso()),
    }


def normalize_curriculum(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_curriculum()
    topics_in = raw.get("topics") or []
    topics: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(topics_in, list):
        for item in topics_in:
            t = normalize_topic(item if isinstance(item, dict) else None)
            if not t:
                continue
            if t["id"] in seen:
                continue
            seen.add(t["id"])
            topics.append(t)
    return {
        "version": CURRICULUM_VERSION,
        "domain": str(raw.get("domain") or "").strip()[:120],
        "source": str(raw.get("source") or "unknown")[:40],
        "fetched_at": raw.get("fetched_at"),
        "fingerprint": str(raw.get("fingerprint") or "")[:64],
        "topics": topics,
        "last_selected_topic_id": (
            str(raw.get("last_selected_topic_id")).strip()
            if raw.get("last_selected_topic_id")
            else None
        ),
    }


def find_topic(curriculum: dict[str, Any], topic_id: str) -> dict[str, Any] | None:
    tid = (topic_id or "").strip()
    if not tid:
        return None
    for t in curriculum.get("topics") or []:
        if isinstance(t, dict) and str(t.get("id")) == tid:
            return t
    return None


def active_topics(curriculum: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in curriculum.get("topics") or []:
        if isinstance(t, dict) and str(t.get("status") or "active") == "active":
            out.append(t)
    return out
