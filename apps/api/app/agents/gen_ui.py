"""Generative UI payloads: structured learning views from document context."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
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
    # 1-based indices into payload.sources (same numbers as [1], [2] in context)
    source_indices: list[int] = Field(default_factory=list)

    @field_validator("source_indices", mode="before")
    @classmethod
    def _coerce_indices(cls, v: Any) -> list[int]:
        if not v:
            return []
        out: list[int] = []
        for x in v:
            try:
                i = int(x)
                if i >= 1:
                    out.append(i)
            except (TypeError, ValueError):
                continue
        # unique, preserve order
        seen: set[int] = set()
        uniq: list[int] = []
        for i in out:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq[:8]


class SourceSnippet(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    filename: str | None = None
    score: float | None = None
    snippet: str


class GenerativeUIPayload(BaseModel):
    """Rendered by the web app as cards (not raw markdown)."""

    type: Literal["generative_ui"] = "generative_ui"
    title: str
    plain_summary: str = Field(
        description="One short paragraph for copy/export and accessibility"
    )
    blocks: list[GenUIBlock] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    sources: list[SourceSnippet] = Field(default_factory=list)
    document_id: str | None = None
    document_filename: str | None = None


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _resolve_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: str | None,
    document_filename: str | None,
) -> Document | None:
    if document_id:
        try:
            did = uuid.UUID(str(document_id).strip())
        except ValueError:
            return None
        doc = db.get(Document, did)
        if doc and doc.workspace_id == workspace_id:
            return doc
        return None
    if document_filename:
        name = document_filename.strip()
        q = (
            db.query(Document)
            .filter(
                Document.workspace_id == workspace_id,
                Document.filename == name,
            )
            .first()
        )
        if q:
            return q
        # case-insensitive contains
        return (
            db.query(Document)
            .filter(
                Document.workspace_id == workspace_id,
                Document.filename.ilike(f"%{name}%"),
            )
            .order_by(Document.created_at.desc())
            .first()
        )
    return None


def _hits_for_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    query: str,
    top_k: int,
) -> list[tuple[Chunk, float]]:
    """Prefer semantic hits on one doc; fall back to first chunks of that doc."""
    hits = retrieve_chunks(
        db,
        workspace_id=workspace_id,
        query=query,
        top_k=min(max(top_k, 3), 12),
        min_score=0.05,
    )
    filtered = [(ch, s) for ch, s in hits if ch.document_id == document_id]
    if filtered:
        return filtered[:top_k]

    chunks = (
        db.query(Chunk)
        .filter(
            Chunk.workspace_id == workspace_id,
            Chunk.document_id == document_id,
        )
        .order_by(Chunk.chunk_index.asc())
        .limit(top_k)
        .all()
    )
    return [(ch, 1.0) for ch in chunks]


def build_learning_ui(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    topic: str,
    focus: str = "",
    document_id: str | None = None,
    document_filename: str | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    """
    Retrieve workspace chunks for `topic` and generate a structured learning UI.

    Optionally scope to one document via document_id or document_filename.
    Returns a JSON-serializable generative_ui payload, or an error dict.
    """
    topic = (topic or "").strip()
    if not topic:
        return {"error": "topic is required"}

    scoped_doc = _resolve_document(
        db,
        workspace_id=workspace_id,
        document_id=document_id,
        document_filename=document_filename,
    )
    if (document_id or document_filename) and not scoped_doc:
        return {
            "error": (
                "Document not found in this workspace. "
                "Use list_documents, then pass document_id or exact filename."
            )
        }

    query = f"{topic} {focus}".strip()
    top_k = min(max(top_k, 3), 12)

    if scoped_doc:
        hits = _hits_for_document(
            db,
            workspace_id=workspace_id,
            document_id=scoped_doc.id,
            query=query,
            top_k=top_k,
        )
        if not hits:
            return {
                "error": (
                    f"No chunks for '{scoped_doc.filename}'. "
                    "Ingest until status is ready, then try again."
                )
            }
    else:
        hits = retrieve_chunks(
            db,
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            min_score=settings.rag_min_score,
        )
        if not hits:
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
    seen_files: set[str] = set()
    sources: list[SourceSnippet] = []
    context_parts: list[str] = []

    for i, (ch, score) in enumerate(hits, start=1):
        doc = db.get(Document, ch.document_id)
        name = doc.filename if doc else "document"
        if name not in seen_files:
            seen_files.add(name)
            source_files.append(name)
        snippet = (ch.content or "")[:280]
        sources.append(
            SourceSnippet(
                index=i,
                chunk_id=str(ch.id),
                document_id=str(ch.document_id),
                filename=name,
                score=round(float(score), 4) if score is not None else None,
                snippet=snippet,
            )
        )
        context_parts.append(f"[{i}] ({name}, score={score:.3f})\n{ch.content}")

    context = "\n\n".join(context_parts)
    focus_line = (
        f"Learner focus: {focus}" if focus.strip() else "Learner focus: general understanding"
    )
    scope_line = (
        f"Document scope: ONLY use excerpts from {scoped_doc.filename}."
        if scoped_doc
        else "Document scope: workspace excerpts below (may include multiple files)."
    )
    max_idx = len(sources)

    prompt = f"""You create structured learning UI from document excerpts for easier understanding.

{focus_line}
{scope_line}
User topic: {topic}

RULES:
- Use ONLY the excerpts. Do not invent facts not supported by them.
- Write simply (clear, short sentences). Good for skimming.
- Prefer concrete terms from the sources.
- For EVERY block, set "source_indices" to 1-based excerpt numbers that support it (e.g. [1, 3]). Only use indices from 1 to {max_idx}.
- Return ONLY valid JSON (no markdown fences) matching this shape:
{{
  "title": "short title",
  "plain_summary": "2-4 sentence overview",
  "blocks": [
    {{"type": "summary", "title": "Overview", "body": "...", "source_indices": [1]}},
    {{"type": "key_points", "title": "Key points", "items": ["...", "..."], "source_indices": [1, 2]}},
    {{"type": "key_terms", "title": "Terms", "terms": [{{"term": "...", "definition": "..."}}], "source_indices": [2]}},
    {{"type": "steps", "title": "How it works", "items": ["step 1", "step 2"], "source_indices": [1]}},
    {{"type": "faq", "title": "FAQ", "faqs": [{{"question": "...", "answer": "..."}}], "source_indices": [3]}},
    {{"type": "callout", "title": "Watch out", "body": "important caveat", "source_indices": [2]}}
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
                        "Be accurate to the excerpts. Always cite source_indices."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"error": f"Failed to generate learning UI: {e}"}

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "title": topic[:80] or "Learning view",
            "plain_summary": raw[:500],
            "blocks": [
                {
                    "type": "summary",
                    "title": "Overview",
                    "body": raw[:2000],
                    "source_indices": [1] if sources else [],
                }
            ],
        }

    try:
        blocks = [GenUIBlock.model_validate(b) for b in (data.get("blocks") or [])][:8]
        # Clamp indices to available sources; default to [1] if model omitted
        for b in blocks:
            b.source_indices = [i for i in b.source_indices if 1 <= i <= max_idx]
            if not b.source_indices and max_idx >= 1:
                b.source_indices = [1]

        payload = GenerativeUIPayload(
            title=str(data.get("title") or topic)[:120],
            plain_summary=str(data.get("plain_summary") or "")[:2000],
            blocks=blocks,
            source_files=source_files,
            sources=sources,
            document_id=str(scoped_doc.id) if scoped_doc else None,
            document_filename=scoped_doc.filename if scoped_doc else None,
        )
    except Exception as e:
        return {"error": f"Invalid generative UI shape: {e}", "raw": data}

    if not payload.plain_summary and payload.blocks:
        for b in payload.blocks:
            if b.body:
                payload.plain_summary = b.body[:500]
                break
        if not payload.plain_summary and payload.blocks[0].items:
            payload.plain_summary = "; ".join(payload.blocks[0].items[:3])

    return payload.model_dump()


def learning_ui_to_note_body(payload: dict[str, Any]) -> str:
    """Turn generative UI into markdown suitable for create_note."""
    lines: list[str] = []
    title = str(payload.get("title") or "Learning notes")
    lines.append(f"# {title}")
    if payload.get("document_filename"):
        lines.append(f"_Source: {payload['document_filename']}_")
    if payload.get("plain_summary"):
        lines.append("")
        lines.append(str(payload["plain_summary"]))
    for b in payload.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        bt = b.get("type") or "section"
        bt_title = b.get("title") or str(bt).replace("_", " ").title()
        lines.append("")
        lines.append(f"## {bt_title}")
        if b.get("body"):
            lines.append(str(b["body"]))
        for item in b.get("items") or []:
            lines.append(f"- {item}")
        for t in b.get("terms") or []:
            if isinstance(t, dict):
                lines.append(f"- **{t.get('term', '')}**: {t.get('definition', '')}")
        for f in b.get("faqs") or []:
            if isinstance(f, dict):
                lines.append(f"**Q: {f.get('question', '')}**")
                lines.append(f"A: {f.get('answer', '')}")
        idxs = b.get("source_indices") or []
        if idxs:
            lines.append(f"_Sources: {', '.join(f'[{i}]' for i in idxs)}_")
    files = payload.get("source_files") or []
    if files:
        lines.append("")
        lines.append(f"_Files: {', '.join(files)}_")
    return "\n".join(lines).strip()
