"""LLM reranking of retrieval candidates.

Runs after hybrid fusion: a single batch LLM call scores each candidate
passage for relevance to the query, and the best top_k are returned. RRF
orders by rank agreement; this reorders by actual answer relevance.

Never raises — any failure (API error, bad JSON, missing scores) falls
back to the incoming (RRF) order so retrieval degrades gracefully.
"""

from __future__ import annotations

import json
import uuid

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk
from app.usage import estimate_tokens, log_usage

_PASSAGE_CHARS = 500


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _rerank_model() -> str:
    return settings.rag_rerank_model or settings.chat_model


def _build_prompt(query: str, candidates: list[tuple[Chunk, float]]) -> str:
    lines = [
        f"[{i}] {(ch.content or '')[:_PASSAGE_CHARS]}"
        for i, (ch, _score) in enumerate(candidates)
    ]
    passages = "\n\n".join(lines)
    return (
        f'Query: "{query}"\n\n'
        "Passages:\n"
        f"{passages}\n\n"
        "Score how well each passage answers the query, 0 (irrelevant) to 10 "
        "(directly answers). Return ONLY a JSON array of objects "
        '{"index": <int>, "score": <number>} for every passage. No prose.'
    )


def _parse_scores(raw: str, n: int) -> dict[int, float]:
    """Parse the judge JSON into {index: score}; tolerate fenced/wrapped output."""
    text = raw.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array in rerank output")
    data = json.loads(text[start : end + 1])
    scores: dict[int, float] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = item.get("score")
        if isinstance(idx, int) and 0 <= idx < n and isinstance(score, (int, float)):
            scores[idx] = float(score)
    if not scores:
        raise ValueError("no usable scores in rerank output")
    return scores


def rerank_chunks(
    query: str,
    candidates: list[tuple[Chunk, float]],
    *,
    top_k: int,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> list[tuple[Chunk, float]]:
    """Reorder candidates by LLM relevance and return the best top_k.

    Display score stays each candidate's cosine (unchanged contract). Falls
    back to the incoming order on any error. `candidates` must already be in
    the desired fallback (RRF) order.
    """
    if len(candidates) <= 1:
        return candidates[:top_k]

    prompt = _build_prompt(query, candidates)
    try:
        resp = _client().chat.completions.create(
            model=_rerank_model(),
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise search relevance judge. Output only JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=512,
        )
        raw = (resp.choices[0].message.content or "").strip()
        scores = _parse_scores(raw, len(candidates))
    except Exception:
        return candidates[:top_k]

    if db is not None:
        usage = getattr(resp, "usage", None)
        log_usage(
            db,
            kind="rerank",
            model=_rerank_model(),
            user_id=user_id,
            workspace_id=workspace_id,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=(
                getattr(usage, "total_tokens", None)
                if usage
                else estimate_tokens(prompt, raw)
            ),
            meta={"candidates": len(candidates), "top_k": top_k},
        )
        db.commit()

    # Stable sort by score desc; missing indices score 0. Enumeration index as
    # the secondary key keeps the original RRF order for ties.
    order = sorted(
        range(len(candidates)),
        key=lambda i: (-scores.get(i, 0.0), i),
    )
    return [candidates[i] for i in order[:top_k]]
