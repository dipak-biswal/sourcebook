import uuid
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agents.profiles import get_profile
from app.agents.web_search import search_web
from app.ingestion.retrieve import retrieve_chunks
from app.models import Document, Note


def build_tools(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_type: str = "general",
):
    """Return tool callables bound to this request's db+tenant and agent profile."""
    profile = get_profile(agent_type)

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
            user_id=user_id,
            usage_meta={"source": "agent_search", "query": query[:200]},
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
    def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
        """
        Search the public web via DuckDuckGo for role requirements, market context,
        benchmarks, or definitions not found in workspace documents.
        Use the current year for time-sensitive queries (skills, requirements, hiring).
        """

        return search_web(query, max_results=max_results)

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

    by_name = {
        "list_documents": list_documents,
        "search_documents": search_documents,
        "web_search": web_search,
        "create_note": create_note,
    }
    return [by_name[name] for name in by_name if name in profile.tool_names]
