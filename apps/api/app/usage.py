import uuid

from sqlalchemy.orm import Session

from app.models import UsageEvent


def log_usage(
    db: Session,
    *,
    kind: str,
    model: str | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    meta: dict | None = None,
) -> UsageEvent:
    """Append a usage row. Caller is responsible for commit."""
    if (
        total_tokens is None
        and prompt_tokens is not None
        and completion_tokens is not None
    ):
        total_tokens = prompt_tokens + completion_tokens

    event = UsageEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        kind=kind,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        meta=meta,
    )
    db.add(event)
    return event


def estimate_tokens(*texts: str) -> int:
    """Rough ~4 chars/token estimate when the provider omits usage."""
    total_chars = sum(len(t or "") for t in texts)
    return max(1, total_chars // 4)
