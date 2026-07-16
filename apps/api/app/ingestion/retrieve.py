import math
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.embeddings import embed_query
from app.ingestion.rerank import rerank_chunks
from app.models import Chunk


def _vector_arm(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    q_vec: list[float],
    limit: int,
) -> list[tuple[Chunk, float, int]]:
    """Top candidates by pgvector cosine. Returns (chunk, cosine, rank)."""
    distance = Chunk.embedding.cosine_distance(q_vec)
    rows = (
        db.query(Chunk, (1 - distance).label("score"))
        .filter(
            Chunk.workspace_id == workspace_id,
            Chunk.embedding.isnot(None),
            Chunk.embedding_model == settings.embedding_model,
        )
        .order_by(distance)
        .limit(limit)
        .all()
    )
    return [(chunk, float(score), rank) for rank, (chunk, score) in enumerate(rows, 1)]


def _keyword_arm(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[tuple[Chunk, float, int]]:
    """Top candidates by Postgres full-text ts_rank. Returns (chunk, rank_score, rank).

    Uses the DB-only generated column chunks.content_tsv (see migration 003).
    websearch_to_tsquery handles empty/stopword queries by yielding no rows.
    Returns [] if FTS is unavailable (pre-migration DB, SQLite tests, etc.) so
    retrieval still works on the vector arm alone.
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        id_rows = db.execute(
            text(
                "SELECT id, ts_rank_cd(content_tsv, q) AS rank "
                "FROM chunks, websearch_to_tsquery('english', :query) AS q "
                "WHERE workspace_id = CAST(:ws AS uuid) "
                "AND embedding_model = :model "
                "AND content_tsv @@ q "
                "ORDER BY rank DESC "
                "LIMIT :limit"
            ),
            {
                "query": q,
                "ws": str(workspace_id),
                "model": settings.embedding_model,
                "limit": limit,
            },
        ).all()
    except Exception:
        return []
    if not id_rows:
        return []

    rank_by_id = {row.id: float(row.rank) for row in id_rows}
    order = {row.id: pos for pos, row in enumerate(id_rows, 1)}
    chunks = db.query(Chunk).filter(Chunk.id.in_(list(rank_by_id))).all()
    chunks.sort(key=lambda c: order[c.id])
    return [(c, rank_by_id[c.id], order[c.id]) for c in chunks]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _fuse(
    vector_hits: list[tuple[Chunk, float, int]],
    keyword_hits: list[tuple[Chunk, float, int]],
    *,
    q_vec: list[float],
    top_k: int,
    rrf_k: int,
) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion over the two arms.

    Ranking is by fused RRF score; the returned display score stays the cosine
    similarity so the UI meaning (and the ~min_score mental model) is unchanged.
    """
    rrf: dict[uuid.UUID, float] = {}
    chunk_by_id: dict[uuid.UUID, Chunk] = {}
    cosine_by_id: dict[uuid.UUID, float] = {}

    for chunk, cosine, rank in vector_hits:
        rrf[chunk.id] = rrf.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)
        chunk_by_id[chunk.id] = chunk
        cosine_by_id[chunk.id] = cosine

    for chunk, _rank_score, rank in keyword_hits:
        rrf[chunk.id] = rrf.get(chunk.id, 0.0) + 1.0 / (rrf_k + rank)
        chunk_by_id.setdefault(chunk.id, chunk)
        if chunk.id not in cosine_by_id:
            # Keyword-only chunk: compute cosine from its embedding for display.
            emb = list(chunk.embedding) if chunk.embedding is not None else []
            cosine_by_id[chunk.id] = _cosine(q_vec, emb)

    ordered = sorted(rrf, key=lambda cid: rrf[cid], reverse=True)[:top_k]
    return [(chunk_by_id[cid], cosine_by_id[cid]) for cid in ordered]


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
    Hybrid retrieval: pgvector cosine + Postgres full-text, fused with RRF.

    Returns up to top_k (chunk, cosine_score) ordered by fused relevance. Does
    NOT fall back to weak matches — off-topic questions return [] so the UI
    shows no sources. Denial fires only when BOTH arms are weak: max cosine
    < min_score AND no keyword row clears rag_keyword_min_rank. Only chunks
    embedded with the current model are considered (mixed vectors aren't
    comparable, and the keyword arm mirrors that filter for consistency).
    """
    q_vec = embed_query(
        query,
        db=db,
        user_id=user_id,
        workspace_id=workspace_id,
        kind=usage_kind,
        meta=usage_meta,
    )

    vector_hits = _vector_arm(
        db,
        workspace_id=workspace_id,
        q_vec=q_vec,
        limit=settings.rag_candidate_k,
    )
    keyword_hits = _keyword_arm(
        db,
        workspace_id=workspace_id,
        query=query,
        limit=settings.rag_candidate_k,
    )

    best_cosine = max((c for _, c, _ in vector_hits), default=0.0)
    best_keyword = max((r for _, r, _ in keyword_hits), default=0.0)
    vector_relevant = best_cosine >= min_score
    keyword_relevant = bool(keyword_hits) and best_keyword > settings.rag_keyword_min_rank
    if not vector_relevant and not keyword_relevant:
        return []

    rerank = settings.rag_rerank_enabled
    pool_k = max(top_k, settings.rag_rerank_candidate_k) if rerank else top_k
    fused = _fuse(
        vector_hits,
        keyword_hits,
        q_vec=q_vec,
        top_k=pool_k,
        rrf_k=settings.rag_rrf_k,
    )
    if rerank and len(fused) > 1:
        return rerank_chunks(
            query,
            fused,
            top_k=top_k,
            db=db,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    return fused[:top_k]
