"""Persist HITL context into workspace settings when fields are empty."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.context.merge import CollectedContextSnapshot
from app.models import Workspace


def apply_snapshot_to_workspace(
    db: Session,
    workspace: Workspace,
    snapshot: CollectedContextSnapshot | None,
) -> dict[str, Any]:
    """
    Fill missing workspace description/tags from HITL answers.

    Never overwrites a non-empty description. Tags are append-only for new labels.
    Invalidates context_cache when anything changes.
    """
    if snapshot is None or snapshot.is_empty():
        return {"updated": False}

    changed: dict[str, Any] = {"updated": False}

    # Description: only if empty
    if not (workspace.description or "").strip():
        parts: list[str] = []
        if snapshot.workspace_framing:
            parts.append(snapshot.workspace_framing.strip())
        if snapshot.topic_focus:
            parts.append(f"Focus: {snapshot.topic_focus.strip()}")
        if snapshot.audience:
            parts.append(f"Audience: {snapshot.audience.strip()}")
        if snapshot.level:
            parts.append(f"Level: {snapshot.level.strip()}")
        if snapshot.must_cover:
            parts.append(f"Must cover: {snapshot.must_cover.strip()}")
        if snapshot.document_plan:
            parts.append(f"Evidence: {snapshot.document_plan.strip()}")
        if parts:
            workspace.description = "\n".join(parts)[:4000]
            changed["description"] = workspace.description
            changed["updated"] = True

    # Tags: append new labels only
    existing = [
        str(t).strip()
        for t in (workspace.tags or [])
        if t is not None and str(t).strip()
    ]
    existing_l = {t.lower() for t in existing}
    candidates: list[str] = []
    for raw in (
        snapshot.level,
        snapshot.audience,
        *(snapshot.extra.values() if snapshot.extra else []),
    ):
        text = (raw or "").strip()
        if not text or "," in text:
            # multi-value strings: take first short token-ish label
            if "," in text:
                for part in text.split(","):
                    p = part.strip()
                    if 1 < len(p) <= 40:
                        candidates.append(p)
            continue
        if len(text) <= 40:
            candidates.append(text)

    added: list[str] = []
    for c in candidates:
        if c.lower() not in existing_l:
            existing.append(c)
            existing_l.add(c.lower())
            added.append(c)
        if len(existing) >= 20:
            break
    if added:
        workspace.tags = existing
        changed["tags_added"] = added
        changed["updated"] = True

    if changed.get("updated"):
        workspace.context_cache = None
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

    return changed
