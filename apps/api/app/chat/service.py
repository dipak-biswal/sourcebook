from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.retrieve import retrieve_chunks
from app.models import Conversation, Message


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _build_answer_from_context(user_text: str, context: str) -> str:
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
    return (resp.choices[0].message.content or "").strip()


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
    )

    if not hits:
        answer = (
            "I don't know — no relevant indexed chunks matched your question. "
            "Upload a .txt/.md, click Ingest until status is ready, then ask again "
            "using terms that appear in the document."
        )
        citations: list[dict] = []
    else:
        context_blocks = []
        citations = []
        for i, (ch, score) in enumerate(hits, start=1):
            context_blocks.append(f"[{i}] (relevance={score:.3f})\n{ch.content}")
            citations.append(
                {
                    "chunk_id": str(ch.id),
                    "document_id": str(ch.document_id),
                    "score": round(score, 4),
                    "snippet": ch.content[:240],
                }
            )
        context = "\n\n".join(context_blocks)
        answer = _build_answer_from_context(user_text, context)

        # If the model still empty-refuses despite good hits, surface a minimal extractive fallback
        if not answer or answer.lower().strip() in {
            "i don't know",
            "i dont know",
            "i don't know.",
            "i dont know.",
        }:
            # Use the best chunk as a grounded fallback so the UI is never empty of content
            best = hits[0][0].content.strip()
            answer = (
                "Based on the retrieved document text:\n\n"
                f"{best[:1200]}"
                f"\n\n[1]"
            )

    asst_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations=citations,
    )

    db.add(asst_msg)
    db.commit()
    db.refresh(user_msg)
    db.refresh(asst_msg)

    return user_msg, asst_msg, citations
