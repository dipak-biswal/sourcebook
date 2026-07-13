import uuid
from collections.abc import Generator
import json

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.retrieve import retrieve_chunks
from app.models import Chunk, Conversation, Document, Message
from app.usage import estimate_tokens, log_usage


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _citation_dict(db: Session, ch, score: float, index: int) -> dict:
    doc = db.get(Document, ch.document_id)
    return {
        "index": index,
        "chunk_id": str(ch.id),
        "document_id": str(ch.document_id),
        "filename": doc.filename if doc else None,
        "score": round(score, 4),
        "snippet": (ch.content or "")[:240],
    }


DENIAL_MESSAGE = (
    "I don't know — no relevant indexed chunks matched your question. "
    "Upload a supported file (PDF, DOCX, txt/md, …), click Ingest until ready, then ask again "
    "using terms that appear in the document."
)


def _build_answer_from_context(
    user_text: str, context: str
) -> tuple[str, object | None]:
    """
    Small local models often over-refuse when the system prompt says
    "if unsure say you don't know". Use an extractive-style prompt instead.
    """
    # Many 1B–3B models follow a single user message more reliably than system+user.
    prompt = f"""You are Sourcebook. Answer the user's question using ONLY the document excerpts below.

RULES:
1. The excerpts ARE your source of truth — use them.
2. Give a direct answer first (2–6 sentences).
3. Quote or paraphrase facts from the excerpts; cite like [1], [2].
4. If the excerpts only partly answer, share what they do contain.
5. Say "I don't know" ONLY if none of the excerpts relate to the question at all.
6. Do not invent facts that are not in the excerpts.

EXCERPTS:
{context}

QUESTION: {user_text}

ANSWER:"""

    resp = _client().chat.completions.create(
        model=settings.chat_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions using provided document excerpts. "
                    "Be helpful and specific. Prefer answering from the excerpts "
                    "over refusing."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    text = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    return text, usage


def run_rag_chat(
    db: Session, *, conversation: Conversation, user_text: str
) -> tuple[Message, Message, list[dict]]:
    user_msg = Message(conversation_id=conversation.id, role="user", content=user_text)
    db.add(user_msg)
    db.flush()

    # Name the session from the first user message so the sidebar list is useful
    if not conversation.title or conversation.title.strip().lower() in {
        "new chat",
        "new conversation",
        "",
    }:
        conversation.title = user_text.strip()[:80] or "New chat"
        db.add(conversation)

    hits = retrieve_chunks(
        db,
        workspace_id=conversation.workspace_id,
        query=user_text,
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        user_id=conversation.user_id,
        usage_meta={"conversation_id": str(conversation.id), "source": "chat"},
    )

    if not hits:
        answer = DENIAL_MESSAGE
        citations: list[dict] = []
        usage = None
    else:
        context_blocks = []
        citations = []
        for i, (ch, score) in enumerate(hits, start=1):
            context_blocks.append(f"[{i}] (relevance={score:.3f})\n{ch.content}")
            citations.append(_citation_dict(db, ch, score, i))
        context = "\n\n".join(context_blocks)
        answer, usage = _build_answer_from_context(user_text, context)

        # If the model still empty-refuses despite good hits, surface a minimal extractive fallback
        if not answer or answer.lower().strip() in {
            "i don't know",
            "i dont know",
            "i don't know.",
            "i dont know.",
        }:
            # Use the best chunk as a grounded fallback so the UI is never empty of content
            best = hits[0][0].content.strip()
            answer = f"Based on the retrieved document text:\n\n{best[:1200]}\n\n[1]"

    asst_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations=citations,
    )

    db.add(asst_msg)
    log_usage(
        db,
        kind="chat",
        model=settings.chat_model if hits else None,
        user_id=conversation.user_id,
        workspace_id=conversation.workspace_id,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        meta={
            "conversation_id": str(conversation.id),
            "estimated": usage is None,
            "denied": not bool(hits),
            "hit_count": len(hits),
        },
    )
    db.commit()
    db.refresh(user_msg)
    db.refresh(asst_msg)

    return user_msg, asst_msg, citations


def iter_rag_chat_sse(
    db: Session, *, conversation: Conversation, user_text: str
) -> Generator[str, None, None]:
    """
    Yields SSE lines:
    data: {"type":"meta","conversation_id":"..."}
    data: {"type":"token","content":"..."}
    data: {"type":"citations","citations":[]}
    data: {"type":"done"}
    data: {"type":"error","detail":"..."}
    """

    user_msg = Message(conversation_id=conversation.id, role="user", content=user_text)

    db.add(user_msg)
    db.flush()

    if not conversation.title or conversation.title.strip().lower() in {
        "new chat",
        "new conversation",
        "",
    }:
        conversation.title = user_text.strip()[:80] or "New chat"
        db.add(conversation)

    hits = retrieve_chunks(
        db,
        workspace_id=conversation.workspace_id,
        query=user_text,
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        user_id=conversation.user_id,
        usage_meta={"conversation_id": str(conversation.id), "source": "chat_stream"},
    )

    yield _sse({"type": "meta", "conversation_id": str(conversation.id)})

    citations: list[dict] = []
    answer_parts: list[str] = []
    usage = None

    if not hits:
        answer = DENIAL_MESSAGE
        yield _sse({"type": "token", "content": answer})
        answer_parts.append(answer)
    else:
        context_blocks = []

        for i, (ch, score) in enumerate(hits, start=1):
            context_blocks.append(f"[{i}] (relevance={score:.3f})\n{ch.content}")
            citations.append(_citation_dict(db, ch, score, i))
        context = "\n\n".join(context_blocks)

        prompt = f"""You are Sourcebook. Answer using ONLY the excerpts below.
        Cite like [1], [2]. Be Concise. Prefer answering from excerpts over refusing.

        EXCERPTS:
        {context}

QUESTION: {user_text}
ANSWER:"""
        client = _client()

        stream = client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "Answer from document excerpts. Be specific and grounded.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            stream=True,
            stream_options={"include_usage": True},
        )

        for event in stream:
            if getattr(event, "usage", None):
                usage = event.usage
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                answer_parts.append(delta)
                yield _sse({"type": "token", "content": delta})

    full_answer = "".join(answer_parts).strip()
    asst_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=full_answer or "(empty)",
        citations=citations,
    )
    db.add(asst_msg)

    if usage is not None:
        log_usage(
            db,
            kind="chat_stream",
            model=settings.chat_model,
            user_id=conversation.user_id,
            workspace_id=conversation.workspace_id,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            meta={
                "conversation_id": str(conversation.id),
                "hit_count": len(hits),
            },
        )
    else:
        log_usage(
            db,
            kind="chat_stream",
            model=settings.chat_model if hits else None,
            user_id=conversation.user_id,
            workspace_id=conversation.workspace_id,
            total_tokens=estimate_tokens(user_text, full_answer),
            meta={
                "conversation_id": str(conversation.id),
                "estimated": True,
                "denied": not bool(hits),
                "hit_count": len(hits),
            },
        )

    db.commit()

    yield _sse({"type": "citations", "citations": citations})
    yield _sse({"type": "done"})


def generate_suggested_questions(
    db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[str]:
    """Suggest 4-6 questions from ready documents in the workspace."""
    docs = (
        db.query(Document)
        .filter(
            Document.workspace_id == workspace_id,
            Document.status == "ready",
        )
        .limit(10)
        .all()
    )

    if not docs:
        return []

    summaries: list[str] = []
    for doc in docs:
        first_chunk = (
            db.query(Chunk)
            .filter(
                Chunk.document_id == doc.id,
                Chunk.content.isnot(None),
            )
            .order_by(Chunk.chunk_index)
            .first()
        )
        snippet = (first_chunk.content or "")[:600] if first_chunk else "(no preview)"
        summaries.append(f"Document: {doc.filename}\nPreview: {snippet}")

    context = "\n\n".join(summaries)

    prompt = f"""You are Sourcebook. Based on these documents in the user's workspace, suggest 4-6 questions they might ask about them.

Rules:
- Each question must be answerable from the document content.
- Cover different documents/topics.
- Be specific — avoid vague questions.
- Return ONLY a JSON array of strings, nothing else.

Documents:
{context}

Questions (JSON array):"""

    resp = _client().chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": "You generate suggested questions from document content."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1024,
    )

    raw = (resp.choices[0].message.content or "").strip()
    usage = resp.usage
    questions: list[str] = []
    try:
        questions = json.loads(raw)
    except json.JSONDecodeError:
        for line in raw.split("\n"):
            line = line.strip().lstrip("0123456789.-) ").strip("-\"")
            if line:
                questions.append(line)

    filtered = [q for q in questions[:6] if isinstance(q, str) and len(q) > 10]

    if usage is not None:
        log_usage(
            db,
            kind="chat_suggestions",
            model=settings.chat_model,
            user_id=user_id,
            workspace_id=workspace_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            meta={"question_count": len(filtered)},
        )
    else:
        log_usage(
            db,
            kind="chat_suggestions",
            model=settings.chat_model,
            user_id=user_id,
            workspace_id=workspace_id,
            total_tokens=estimate_tokens(context, raw),
            meta={"question_count": len(filtered), "estimated": True},
        )
    db.commit()

    return filtered


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
