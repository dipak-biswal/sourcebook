"""Load/save curriculum on Workspace.curriculum JSON column."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.curriculum.schema import (
    find_topic,
    normalize_curriculum,
    normalize_topic,
)
from app.models import Workspace


def fingerprint_for(
    *,
    name: str,
    description: str | None,
    tags: list[str] | None,
    docs_url: str | None = None,
) -> str:
    raw = (
        f"{name or ''}\n{description or ''}\n"
        f"{','.join(sorted(str(t) for t in (tags or []) if t))}\n"
        f"{(docs_url or '').strip()}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def get_curriculum(workspace: Workspace) -> dict[str, Any]:
    return normalize_curriculum(workspace.curriculum)


def save_curriculum(
    db: Session,
    workspace: Workspace,
    curriculum: dict[str, Any],
) -> dict[str, Any]:
    norm = normalize_curriculum(curriculum)
    workspace.curriculum = norm
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return norm


def upsert_topic(
    db: Session,
    workspace: Workspace,
    topic: dict[str, Any],
    *,
    select: bool = False,
) -> dict[str, Any]:
    cur = get_curriculum(workspace)
    t = normalize_topic(topic)
    if not t:
        raise ValueError("invalid topic")
    topics = list(cur.get("topics") or [])
    replaced = False
    for i, existing in enumerate(topics):
        if isinstance(existing, dict) and existing.get("id") == t["id"]:
            # Preserve preferences if new topic omits them
            if not t.get("preferences") and existing.get("preferences"):
                t["preferences"] = existing["preferences"]
            topics[i] = t
            replaced = True
            break
    if not replaced:
        topics.append(t)
    cur["topics"] = topics
    if select:
        cur["last_selected_topic_id"] = t["id"]
    return save_curriculum(db, workspace, cur)


def update_topic_preferences(
    db: Session,
    workspace: Workspace,
    topic_id: str,
    preferences: dict[str, list[str]],
) -> dict[str, Any]:
    cur = get_curriculum(workspace)
    topic = find_topic(cur, topic_id)
    if not topic:
        raise KeyError(topic_id)
    topic = dict(topic)
    topic["preferences"] = {
        str(k): [str(x) for x in (v or []) if str(x).strip()]
        for k, v in (preferences or {}).items()
        if str(k).strip()
    }
    from app.curriculum.schema import _now_iso

    topic["updated_at"] = _now_iso()
    return upsert_topic(db, workspace, topic, select=True)


def set_last_selected(
    db: Session,
    workspace: Workspace,
    topic_id: str | None,
) -> dict[str, Any]:
    cur = get_curriculum(workspace)
    cur["last_selected_topic_id"] = topic_id
    return save_curriculum(db, workspace, cur)
