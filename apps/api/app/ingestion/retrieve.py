import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.embeddings import embed_query
from app.models import Chunk


def retrieve_chunks(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    min_score: float = 0.2,
    user_id: uuid.UUID | None = None,
    usage_kind: str = "embedding_query",
    usage_meta: dict | None = None,
) -> list[tuple[Chunk, float]]:
    """
    Return top-k chunks with cosine score >= min_score, via pgvector HNSW.

    Does NOT fall back to weak matches — off-topic questions should return []
    so the UI shows no sources. Only chunks embedded with the current
    embedding model are considered (mixed-model vectors are not comparable).
    """
    q_vec = embed_query(
        query,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind=usage_kind,
        meta=usage_meta,
    )
    distance = Chunk.embedding.cosine_distance(q_vec)
    rows = (
        db.query(Chunk, (1 - distance).label("score"))
        .filter(
            Chunk.workspace_id == workspace_id,
            Chunk.embedding.isnot(None),
            Chunk.embedding_model == settings.embedding_model,
        )
        .order_by(distance)
        .limit(top_k)
        .all()
    )
    return [(chunk, float(score)) for chunk, score in rows if score >= min_score]
