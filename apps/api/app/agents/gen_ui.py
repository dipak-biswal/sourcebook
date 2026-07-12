"""Generative UI payloads: structured learning views from document context."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.retrieve import retrieve_chunks
from app.models import Chunk, Document


BlockType = Literal[
    "summary",
    "key_points",
    "key_terms",
    "faq",
    "callout",
    "steps",
]


class KeyTerm(BaseModel):
    term: str
    definition: str


class FaqItem(BaseModel):
    question: str
    answer: str


class GenUIBlock(BaseModel):
    type: BlockType
    title: str | None = None
    body: str | None = None
    items: list[str] | None = None
    terms: list[KeyTerm] | None = None
    faqs: list[FaqItem] | None = None


class GenerativeUIPayload(BaseModel):
    """Rendered by the web app as cards (not raw markdown)."""

    type: Literal["generative_ui"] = "generative_ui"
    title: str
    plain_summary: str = Field(
        description="One short paragraph for copy/export and accessibility"
    )
    blocks: list[GenUIBlock] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _context_from_hits(hits: list[tuple[Chunk, float]]) -> tuple[str, list[str]]:
    blocks: list[str] = []
    files: list[str] = []
    seen: set[str] = set()
    for i, (ch, score) in enumerate(hits, start=1):
        # filename resolved by caller when possible
        blocks.append(f"[{i}] (score={score:.3f})\n{ch.content}")
    return "\n\n".join(blocks), files


def build_learning_ui(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    topic: str,
    focus: str = "",
    top_k: int = 8,
) -> dict[str, Any]:
    """
    Retrieve workspace chunks for `topic` and generate a structured learning UI.

    Returns a JSON-serializable generative_ui payload, or an error dict.
    """
    topic = (topic or "").strip()
    if not topic:
        return {"error": "topic is required"}

    query = f"{topic} {focus}".strip()
    hits = retrieve_chunks(
        db,
        workspace_id=workspace_id,
        query=query,
        top_k=min(max(top_k, 3), 12),
        min_score=settings.rag_min_score,
    )
    if not hits:
        # Fallback: any ready docs' first chunks if topic is generic "overview"
        ready_docs = (
            db.query(Document)
            .filter(
                Document.workspace_id == workspace_id,
                Document.status == "ready",
            )
            .limit(5)
            .all()
        )
        if not ready_docs:
            return {
                "error": (
                    "No indexed document content found. "
                    "Upload .txt/.md and Ingest until status is ready."
                )
            }
        # Broad retrieval without min_score for overview-style asks
        hits = retrieve_chunks(
            db,
            workspace_id=workspace_id,
            query=topic or "overview summary main points",
            top_k=8,
            min_score=0.05,
        )
        if not hits:
            return {
                "error": (
                    "Could not retrieve chunks for this workspace. "
                    "Re-ingest documents and try again."
                )
            }

    source_files: list[str] = []
    seen: set[str] = set()
    context_parts: list[str] = []
    for i, (ch, score) in enumerate(hits, start=1):
        doc = db.get(Document, ch.document_id)
        name = doc.filename if doc else "document"
        if name not in seen:
            seen.add(name)
            source_files.append(name)
        context_parts.append(f"[{i}] ({name}, score={score:.3f})\n{ch.content}")

    context = "\n\n".join(context_parts)
    focus_line = f"Learner focus: {focus}" if focus.strip() else "Learner focus: general understanding"

    prompt = f"""You create structured learning UI from document excerpts for easier understanding.

{focus_line}
User topic: {topic}

RULES:
- Use ONLY the excerpts. Do not invent facts not supported by them.
- Write simply (clear, short sentences). Good for skimming.
- Prefer concrete terms from the sources.
- Return ONLY valid JSON (no markdown fences) matching this shape:
{{
  "title": "short title",
  "plain_summary": "2-4 sentence overview",
  "blocks": [
    {{"type": "summary", "title": "Overview", "body": "..."}},
    {{"type": "key_points", "title": "Key points", "items": ["...", "..."]}},
    {{"type": "key_terms", "title": "Terms", "terms": [{{"term": "...", "definition": "..."}}]}},
    {{"type": "steps", "title": "How it works", "items": ["step 1", "step 2"]}},
    {{"type": "faq", "title": "FAQ", "faqs": [{{"question": "...", "answer": "..."}}]}},
    {{"type": "callout", "title": "Watch out", "body": "important caveat"}}
  ]
}}
- Include 3–6 blocks. Always include summary + key_points when possible.
- key_terms: 3–8 terms. faq: 2–5 items. items arrays: 3–7 bullets.

EXCERPTS:
{context}
"""

    try:
        resp = _client().chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You output only JSON for a generative learning UI. "
                        "Be accurate to the excerpts."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1800,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"error": f"Failed to generate learning UI: {e}"}

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: wrap as single summary block
        data = {
            "title": topic[:80] or "Learning view",
            "plain_summary": raw[:500],
            "blocks": [
                {
                    "type": "summary",
                    "title": "Overview",
                    "body": raw[:2000],
                }
            ],
        }

    try:
        payload = GenerativeUIPayload(
            title=str(data.get("title") or topic)[:120],
            plain_summary=str(data.get("plain_summary") or "")[:2000],
            blocks=[GenUIBlock.model_validate(b) for b in (data.get("blocks") or [])][
                :8
            ],
            source_files=source_files,
        )
    except Exception as e:
        return {"error": f"Invalid generative UI shape: {e}", "raw": data}

    if not payload.plain_summary and payload.blocks:
        # Prefer first summary body
        for b in payload.blocks:
            if b.body:
                payload.plain_summary = b.body[:500]
                break
        if not payload.plain_summary and payload.blocks[0].items:
            payload.plain_summary = "; ".join(payload.blocks[0].items[:3])

    return payload.model_dump()
