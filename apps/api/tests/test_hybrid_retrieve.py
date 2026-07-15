"""Unit tests for hybrid RRF fusion (no Postgres required)."""

import uuid
from types import SimpleNamespace

from app.ingestion.retrieve import _cosine, _fuse


def _chunk(embedding: list[float] | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), embedding=embedding)


def test_fuse_prefers_chunk_in_both_arms():
    a = _chunk([1.0, 0.0, 0.0])
    b = _chunk([0.0, 1.0, 0.0])
    q = [1.0, 0.0, 0.0]
    # a ranks 1st vector + 1st keyword; b only 2nd vector
    fused = _fuse(
        [(a, 0.9, 1), (b, 0.5, 2)],
        [(a, 0.8, 1)],
        q_vec=q,
        top_k=2,
        rrf_k=60,
    )
    assert fused[0][0].id == a.id
    assert fused[0][1] == 0.9


def test_fuse_includes_keyword_only_with_computed_cosine():
    a = _chunk([1.0, 0.0, 0.0])
    b = _chunk([0.9, 0.1, 0.0])
    q = [1.0, 0.0, 0.0]
    fused = _fuse(
        [(a, 0.99, 1)],
        [(b, 0.5, 1)],
        q_vec=q,
        top_k=2,
        rrf_k=60,
    )
    ids = {c.id for c, _ in fused}
    assert a.id in ids and b.id in ids
    b_score = next(s for c, s in fused if c.id == b.id)
    assert b_score == _cosine(q, [0.9, 0.1, 0.0])


def test_cosine_handles_mismatched_lengths():
    assert _cosine([1.0, 0.0], [1.0]) == 0.0
    assert _cosine([], [1.0]) == 0.0
