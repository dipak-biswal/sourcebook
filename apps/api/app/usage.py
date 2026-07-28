import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import UsageEvent

# Keep JSON meta under control — full prompts can be large.
_META_TEXT_LIMIT = 12_000


def truncate_for_meta(text: str | None, *, limit: int = _META_TEXT_LIMIT) -> str:
    """Clip text for storage on UsageEvent.meta."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 20] + "\n…[truncated]"


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
    prompt: str | None = None,
    completion: str | None = None,
    tool_name: str | None = None,
    tool_input: Any = None,
    tool_output: Any = None,
) -> UsageEvent:
    """Append a usage row. Caller is responsible for commit.

    Optional prompt/completion/tool_* are merged into meta for workspace
    activity audit (Settings → Workspace detail).
    """
    if (
        total_tokens is None
        and prompt_tokens is not None
        and completion_tokens is not None
    ):
        total_tokens = prompt_tokens + completion_tokens

    meta_out: dict[str, Any] = dict(meta) if isinstance(meta, dict) else {}
    if prompt is not None:
        meta_out["prompt"] = truncate_for_meta(prompt)
    if completion is not None:
        meta_out["completion"] = truncate_for_meta(
            completion if isinstance(completion, str) else str(completion)
        )
    if tool_name:
        meta_out["tool_name"] = str(tool_name)[:100]
    if tool_input is not None:
        meta_out["tool_input"] = _jsonish_clip(tool_input)
    if tool_output is not None:
        meta_out["tool_output"] = _jsonish_clip(tool_output)

    event = UsageEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        kind=kind,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        meta=meta_out or None,
    )
    db.add(event)
    return event


def _jsonish_clip(value: Any, *, limit: int = 8_000) -> Any:
    """Clip nested JSON-ish values for meta storage."""
    if value is None:
        return None
    if isinstance(value, str):
        return truncate_for_meta(value, limit=limit)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        size = 0
        for k, v in list(value.items())[:40]:
            clipped = _jsonish_clip(v, limit=max(400, limit // 4))
            out[str(k)[:80]] = clipped
            size += len(str(clipped))
            if size > limit:
                out["…"] = "truncated"
                break
        return out
    if isinstance(value, list):
        out_list: list[Any] = []
        size = 0
        for item in value[:30]:
            clipped = _jsonish_clip(item, limit=max(400, limit // 4))
            out_list.append(clipped)
            size += len(str(clipped))
            if size > limit:
                out_list.append("…[truncated]")
                break
        return out_list
    return truncate_for_meta(str(value), limit=limit)


def estimate_tokens(*texts: str) -> int:
    """Rough ~4 chars/token estimate when the provider omits usage."""
    total_chars = sum(len(t or "") for t in texts)
    return max(1, total_chars // 4)
