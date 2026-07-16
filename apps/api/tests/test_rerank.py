"""LLM reranking of retrieval candidates."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.ingestion.rerank as rerank_mod
from app.ingestion.rerank import rerank_chunks


class FakeChunk:
    """Minimal stand-in for models.Chunk (rerank only touches .content)."""

    def __init__(self, content: str):
        self.id = uuid.uuid4()
        self.content = content


def _candidates(*texts_with_cosine) -> list[tuple[FakeChunk, float]]:
    return [(FakeChunk(t), c) for t, c in texts_with_cosine]


def _fake_openai(json_content: str) -> MagicMock:
    """OpenAI client whose chat completion returns json_content."""
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json_content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    return client


def test_reranks_by_score_and_trims_top_k():
    cands = _candidates(("alpha", 0.30), ("bravo", 0.90), ("charlie", 0.10))
    # Judge prefers index 2, then 0, then 1
    payload = '[{"index":0,"score":4},{"index":1,"score":1},{"index":2,"score":9}]'
    with patch.object(rerank_mod, "_client", return_value=_fake_openai(payload)):
        out = rerank_chunks("q", cands, top_k=2)
    assert [c.content for c, _ in out] == ["charlie", "alpha"]
    # Display score stays the candidate's cosine (charlie=0.10, alpha=0.30)
    assert [s for _, s in out] == [0.10, 0.30]


def test_malformed_json_falls_back_to_input_order():
    cands = _candidates(("a", 0.5), ("b", 0.4), ("c", 0.3))
    with patch.object(rerank_mod, "_client", return_value=_fake_openai("not json at all")):
        out = rerank_chunks("q", cands, top_k=2)
    assert [c.content for c, _ in out] == ["a", "b"]  # incoming (RRF) order


def test_client_exception_falls_back_and_does_not_raise():
    cands = _candidates(("a", 0.5), ("b", 0.4))
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("boom")
    with patch.object(rerank_mod, "_client", return_value=client):
        out = rerank_chunks("q", cands, top_k=5)
    assert [c.content for c, _ in out] == ["a", "b"]


def test_equal_scores_preserve_input_order():
    cands = _candidates(("first", 0.5), ("second", 0.4), ("third", 0.3))
    payload = '[{"index":0,"score":5},{"index":1,"score":5},{"index":2,"score":5}]'
    with patch.object(rerank_mod, "_client", return_value=_fake_openai(payload)):
        out = rerank_chunks("q", cands, top_k=3)
    assert [c.content for c, _ in out] == ["first", "second", "third"]


def test_missing_index_scored_zero_and_ranked_last():
    cands = _candidates(("a", 0.5), ("b", 0.4))
    # Only index 1 scored; index 0 defaults to 0 and drops below it
    payload = '[{"index":1,"score":8}]'
    with patch.object(rerank_mod, "_client", return_value=_fake_openai(payload)):
        out = rerank_chunks("q", cands, top_k=2)
    assert [c.content for c, _ in out] == ["b", "a"]


def test_single_candidate_skips_llm():
    cands = _candidates(("only", 0.7))
    client = MagicMock()
    with patch.object(rerank_mod, "_client", return_value=client):
        out = rerank_chunks("q", cands, top_k=5)
    assert [c.content for c, _ in out] == ["only"]
    client.chat.completions.create.assert_not_called()


def test_retrieve_bypasses_rerank_when_disabled(monkeypatch):
    """rag_rerank_enabled=False → retrieve_chunks returns fused order untouched."""
    import app.ingestion.retrieve as retrieve_mod

    fused = _candidates(("x", 0.9), ("y", 0.8))
    monkeypatch.setattr(retrieve_mod.settings, "rag_rerank_enabled", False)
    monkeypatch.setattr(retrieve_mod, "embed_query", lambda *a, **k: [0.1, 0.2])
    monkeypatch.setattr(
        retrieve_mod, "_vector_arm", lambda *a, **k: [(fused[0][0], 0.9, 1)]
    )
    monkeypatch.setattr(retrieve_mod, "_keyword_arm", lambda *a, **k: [])
    monkeypatch.setattr(retrieve_mod, "_fuse", lambda *a, **k: fused)
    # If rerank were called it would hit the network; assert it is not.
    called = {"n": 0}
    monkeypatch.setattr(
        retrieve_mod, "rerank_chunks", lambda *a, **k: called.__setitem__("n", 1) or fused
    )
    out = retrieve_mod.retrieve_chunks(
        None, workspace_id=uuid.uuid4(), query="q", top_k=1, min_score=0.22
    )
    assert called["n"] == 0
    assert [c.content for c, _ in out] == ["x"]  # trimmed to top_k, no rerank
