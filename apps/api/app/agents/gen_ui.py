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


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, list):
        out: list[str] = []
        for x in value:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                # {"text": "..."} or {"point": "..."}
                for k in ("text", "point", "item", "value", "content"):
                    if k in x and str(x[k]).strip():
                        out.append(str(x[k]).strip())
                        break
            else:
                t = str(x).strip()
                if t:
                    out.append(t)
        return out
    return []


def _normalize_block_dict(raw: Any) -> dict[str, Any] | None:
    """
    Coerce common LLM shape variants so cards are not empty titles only.
    Models often use content/points/bullets/glossary/questions instead of our schema.
    """
    if not isinstance(raw, dict):
        return None
    b = dict(raw)

    # type aliases
    t = str(b.get("type") or b.get("kind") or b.get("block_type") or "summary").lower()
    type_map = {
        "overview": "summary",
        "intro": "summary",
        "introduction": "summary",
        "bullets": "key_points",
        "bullet_points": "key_points",
        "points": "key_points",
        "highlights": "key_points",
        "takeaways": "key_points",
        "glossary": "key_terms",
        "definitions": "key_terms",
        "vocabulary": "key_terms",
        "terms": "key_terms",
        "questions": "faq",
        "q_and_a": "faq",
        "qna": "faq",
        "howto": "steps",
        "how_to": "steps",
        "procedure": "steps",
        "process": "steps",
        "warning": "callout",
        "note": "callout",
        "tip": "callout",
        "important": "callout",
    }
    b["type"] = type_map.get(t, t if t in {
        "summary", "key_points", "key_terms", "faq", "callout", "steps"
    } else "summary")

    # title
    if not b.get("title"):
        for k in ("heading", "name", "label"):
            if b.get(k):
                b["title"] = str(b[k])
                break

    # body text aliases
    body = b.get("body") or b.get("content") or b.get("text") or b.get("description") or b.get("summary")
    if body is not None and not isinstance(body, str):
        body = str(body)
    if body:
        b["body"] = body.strip()

    # list aliases
    items = (
        b.get("items")
        or b.get("points")
        or b.get("bullets")
        or b.get("key_points")
        or b.get("steps")
        or b.get("list")
    )
    items_list = _as_str_list(items)
    if items_list:
        b["items"] = items_list

    # terms / glossary
    terms_raw = b.get("terms") or b.get("glossary") or b.get("definitions") or b.get("vocabulary")
    terms_out: list[dict[str, str]] = []
    if isinstance(terms_raw, list):
        for x in terms_raw:
            if not isinstance(x, dict):
                continue
            term = x.get("term") or x.get("name") or x.get("word") or x.get("key")
            definition = (
                x.get("definition")
                or x.get("meaning")
                or x.get("desc")
                or x.get("description")
                or x.get("value")
            )
            if term and definition:
                terms_out.append(
                    {"term": str(term).strip(), "definition": str(definition).strip()}
                )
    if terms_out:
        b["terms"] = terms_out

    # faq aliases
    faqs_raw = b.get("faqs") or b.get("faq") or b.get("questions") or b.get("qas")
    faqs_out: list[dict[str, str]] = []
    if isinstance(faqs_raw, list):
        for x in faqs_raw:
            if not isinstance(x, dict):
                continue
            q = x.get("question") or x.get("q") or x.get("prompt")
            a = x.get("answer") or x.get("a") or x.get("response")
            if q and a:
                faqs_out.append({"question": str(q).strip(), "answer": str(a).strip()})
    if faqs_out:
        b["faqs"] = faqs_out

    # If model put a list into body only, split to items for list-like types
    if b["type"] in ("key_points", "steps") and not b.get("items") and b.get("body"):
        parts = re.split(r"[\n;•]+", str(b["body"]))
        cleaned = [p.strip(" -*\t") for p in parts if p.strip(" -*\t")]
        if len(cleaned) >= 2:
            b["items"] = cleaned
            # keep body as short intro optional — clear to avoid duplicate
            b.pop("body", None)

    # Drop blocks with no renderable content
    has_content = bool(
        b.get("body")
        or b.get("items")
        or b.get("terms")
        or b.get("faqs")
    )
    if not has_content:
        return None

    # source indices aliases
    si = b.get("source_indices") or b.get("sources") or b.get("citations") or b.get("refs")
    if si is not None:
        b["source_indices"] = si

    return b


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
                        "Upload a supported file (PDF, DOCX, txt/md, …) and Ingest until ready."
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
- Return ONLY valid JSON (no markdown fences) matching this shape EXACTLY
  (use these field names: body, items, terms, faqs — not content/points/glossary):
{{
  "title": "short title",
  "plain_summary": "2-4 sentence overview",
  "blocks": [
    {{"type": "summary", "title": "Overview", "body": "full paragraph text here", "source_indices": [1]}},
    {{"type": "key_points", "title": "Key points", "items": ["point one", "point two", "point three"], "source_indices": [1, 2]}},
    {{"type": "key_terms", "title": "Terms", "terms": [{{"term": "Word", "definition": "simple meaning"}}], "source_indices": [2]}},
    {{"type": "steps", "title": "How it works", "items": ["step 1", "step 2"], "source_indices": [1]}},
    {{"type": "faq", "title": "FAQ", "faqs": [{{"question": "Q?", "answer": "A."}}], "source_indices": [3]}},
    {{"type": "callout", "title": "Watch out", "body": "important caveat", "source_indices": [2]}}
  ]
}}
- CRITICAL: never return empty blocks (title only). Every block MUST include body and/or items and/or terms and/or faqs with real text from the excerpts.
- Include 3–6 blocks. Always include summary (with body) + key_points (with items) when possible.
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

    # Accept top-level content aliases
    plain = (
        data.get("plain_summary")
        or data.get("summary")
        or data.get("overview")
        or data.get("description")
        or ""
    )

    raw_blocks = data.get("blocks") or data.get("sections") or data.get("cards") or []
    if not isinstance(raw_blocks, list):
        raw_blocks = []

    blocks: list[GenUIBlock] = []
    for raw_b in raw_blocks[:10]:
        norm = _normalize_block_dict(raw_b)
        if not norm:
            continue
        try:
            block = GenUIBlock.model_validate(norm)
        except Exception:
            continue
        block.source_indices = [i for i in block.source_indices if 1 <= i <= max_idx]
        if not block.source_indices and max_idx >= 1:
            block.source_indices = [1]
        blocks.append(block)
        if len(blocks) >= 8:
            break

    # Guarantee at least one contentful block from sources if model returned empty cards
    if not blocks and sources:
        first = sources[0]
        blocks = [
            GenUIBlock(
                type="summary",
                title="Overview",
                body=(first.snippet or topic)[:1500],
                source_indices=[1],
            ),
            GenUIBlock(
                type="key_points",
                title="From your documents",
                items=[
                    (s.snippet[:160] + ("…" if len(s.snippet) > 160 else ""))
                    for s in sources[:5]
                    if s.snippet
                ],
                source_indices=list(range(1, min(len(sources), 5) + 1)),
            ),
        ]

    try:
        payload = GenerativeUIPayload(
            title=str(data.get("title") or data.get("heading") or topic)[:120],
            plain_summary=str(plain or "")[:2000],
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
        if not payload.plain_summary and sources:
            payload.plain_summary = (sources[0].snippet or "")[:400]

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
