import math
import uuid

from sqlalchemy.orm import Session

from app.ingestion.embeddings import embed_query
from app.models import Chunk


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))

    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def retrieve_chunks(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    min_score: float = 0.2,
) -> list[tuple[Chunk, float]]:
    """
    Return top-k chunks with cosine score >= min_score.

    Does NOT fall back to weak matches — off-topic questions should return []
    so the UI shows no sources.
    """
    q_vec = embed_query(query)
    chunks = (
        db.query(Chunk)
        .filter(
            Chunk.workspace_id == workspace_id,
            Chunk.embedding.isnot(None),
        )
        .all()
    )
    scored: list[tuple[Chunk, float]] = []

    for ch in chunks:
        if not ch.embedding:
            continue
        score = _cosine(q_vec, list(ch.embedding))
        if score >= min_score:
            scored.append((ch, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
