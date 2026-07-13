import uuid

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.usage import estimate_tokens, log_usage


def get_embedding_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def embed_texts(
    texts: list[str],
    *,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    kind: str = "embedding",
    meta: dict | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    client = get_embedding_client()

    resp = client.embeddings.create(model=settings.embedding_model, input=texts)

    if db is not None and user_id is not None:
        usage = resp.usage
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        estimated = False
        if total_tokens is None:
            total_tokens = estimate_tokens(*texts)
            estimated = True
        log_usage(
            db,
            kind=kind,
            model=settings.embedding_model,
            user_id=user_id,
            workspace_id=workspace_id,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            meta={
                **(meta or {}),
                "text_count": len(texts),
                **({"estimated": True} if estimated else {}),
            },
        )
        db.commit()

    sorted_data = sorted(resp.data, key=lambda d: d.index)

    return [item.embedding for item in sorted_data]


def embed_query(
    text: str,
    *,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    kind: str = "embedding_query",
    meta: dict | None = None,
) -> list[float]:
    return embed_texts(
        [text],
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind=kind,
        meta=meta,
    )[0]