import uuid
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agents.gen_ui import build_learning_ui
from app.ingestion.retrieve import retrieve_chunks
from app.models import Document, Note


def build_tools(db: Session, *, workspace_id: uuid.UUID, user_id: uuid.UUID):
    """Return tool callables bound to this request's db+tenant."""

    @tool
    def list_documents() -> list[dict[str, Any]]:
        """List documents in the current workspace (id, filename, status)."""

        docs = (
            db.query(Document)
            .filter(Document.workspace_id == workspace_id)
            .order_by(Document.created_at.desc())
            .limit(50)
            .all()
        )

        return [
            {"id": str(d.id), "filename": d.filename, "status": d.status} for d in docs
        ]

    @tool
    def search_documents(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search over ingested document chunks in this workspace."""

        hits = retrieve_chunks(
            db,
            workspace_id=workspace_id,
            query=query,
            top_k=min(top_k, 10),
        )

        results = []

        for ch, score in hits:
            doc = db.get(Document, ch.document_id)
            results.append(
                {
                    "chunk_id": str(ch.id),
                    "document_id": str(ch.document_id),
                    "filename": doc.filename if doc else None,
                    "score": round(score, 4),
                    "snippet": (ch.content or "")[:400],
                }
            )
        return results

    @tool
    def explain_for_learners(topic: str, focus: str = "") -> dict[str, Any]:
        """
        Generate an easy-to-understand learning UI from uploaded documents.

        Use when the user wants a simple overview, key points, glossary, FAQ,
        or structured explanation of content in their workspace docs.
        Returns a generative_ui payload (cards/blocks) for the frontend.
        """
        return build_learning_ui(
            db,
            workspace_id=workspace_id,
            topic=topic,
            focus=focus or "",
        )

    @tool
    def create_note(title: str, body: str = "") -> dict[str, Any]:
        """
        Create a note in the workspace.
        Write tool — requires human approval before it executes.
        """

        note = Note(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title.strip() or "Untitled",
            body=body or "",
        )

        db.add(note)
        db.flush()
        return {
            "id": str(note.id),
            "title": note.title,
            "body": note.body,
            "status": "created",
        }

    return [
        list_documents,
        search_documents,
        explain_for_learners,
        create_note,
    ]
