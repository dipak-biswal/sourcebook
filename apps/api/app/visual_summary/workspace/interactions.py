"""User interaction signals for Visual Summary affordance ranking.

Chip clicks, FAQ expands, and related UI events are logged as zero-token
usage rows (`kind=visual_interaction`). On the next plan they become soft
boosts so layouts converge on what each workspace's users actually open.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import UsageEvent
from app.usage import log_usage

# UI action → affordance id (must be in blocks.AFFORDANCE_SPEC).
ACTION_TO_AFFORDANCE: dict[str, str] = {
    "chip_select": "topic_filter",
    "chip_click": "topic_filter",
    "faq_expand": "self_check",
    "filter_select": "topic_filter",
}

ALLOWED_ACTIONS = frozenset(ACTION_TO_AFFORDANCE) | frozenset(
    {
        # Explicit affordance targets (advanced / future blocks).
        "affordance_open",
    }
)

# log2-ish dampening: 1 click ≈ 1.0, 3 ≈ 1.6, 7 ≈ 2.0, 15 ≈ 2.5 (capped later)
def _count_to_boost(count: int) -> float:
    if count <= 0:
        return 0.0
    # log2(count + 1) keeps early clicks meaningful without runaway.
    import math

    return round(math.log2(count + 1), 4)


def log_visual_interaction(
    db: Session,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    action: str,
    affordance: str | None = None,
    label: str | None = None,
    run_id: str | None = None,
) -> UsageEvent:
    """Record a lightweight interaction. Caller commits."""
    action = (action or "").strip().lower()
    mapped = ACTION_TO_AFFORDANCE.get(action)
    target = (affordance or mapped or "").strip()
    return log_usage(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind="visual_interaction",
        model=None,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        meta={
            "action": action,
            "affordance": target or None,
            "label": (label or "")[:120] or None,
            "run_id": run_id,
        },
    )


def interaction_boosts_for_workspace(
    db: Session,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 200,
) -> dict[str, float]:
    """Aggregate recent visual_interaction rows into per-affordance boosts."""
    rows = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.user_id == user_id,
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.kind == "visual_interaction",
        )
        .order_by(UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return boosts_from_interaction_rows(rows)


def boosts_from_interaction_rows(rows: list[Any]) -> dict[str, float]:
    """Pure fold of usage-like rows → {affordance: boost}. Unit-testable offline."""
    counts: dict[str, int] = {}
    for row in rows:
        meta = getattr(row, "meta", None)
        if not isinstance(meta, dict):
            continue
        action = str(meta.get("action") or "").strip().lower()
        aff = str(meta.get("affordance") or "").strip()
        if not aff:
            aff = ACTION_TO_AFFORDANCE.get(action, "")
        if not aff:
            continue
        counts[aff] = counts.get(aff, 0) + 1
    return {aff: _count_to_boost(n) for aff, n in counts.items() if n > 0}
