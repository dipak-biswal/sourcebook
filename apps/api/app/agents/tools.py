import uuid
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.agents.date_tools import get_current_date
from app.agents.fetch_url import fetch_url_content
from app.agents.profiles import get_profile
from app.agents.tool_policy import GENERAL_TOOL_ORDER
from app.agents.visual_tools import build_visual_tools
from app.presentation.context import PresentationContext
from app.agents.web_search import search_web
from app.ingestion.retrieve import retrieve_chunks
from app.models import Chunk, Document, Note


def build_tools(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_type: str = "general",
    presentation_context: PresentationContext | None = None,
    allow_web_search: bool = True,
):
    """Return tool callables bound to this request's db+tenant and agent profile."""
    profile = get_profile(agent_type)

    if profile.agent_type == "visual_summary":
        if presentation_context is None:
            raise ValueError("presentation_context is required for visual_summary tools")
        return build_visual_tools(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            ctx=presentation_context,
        )

    tool_names = set(profile.tool_names)
    if not allow_web_search:
        tool_names.discard("web_search")
        tool_names.discard("fetch_url")

    @tool
    def list_documents() -> list[dict[str, Any]]:
        """
        List documents in the current workspace (id, filename, status).
        Call get_current_date first if you have not already in this run.
        """

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
        """
        Semantic search over ingested document chunks in this workspace.
        Call get_current_date first if you have not already in this run.
        """

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
    def read_document(
        document_id: str, start_chunk: int = 0, max_chunks: int = 6
    ) -> dict[str, Any]:
        """
        Read the full text of one workspace document, in chunk order.
        Use after list_documents/search_documents when snippets are not enough.
        Paginate with start_chunk/max_chunks; has_more and next_start_chunk
        tell you how to continue.
        """

        try:
            doc_uuid = uuid.UUID(document_id)
        except (ValueError, AttributeError, TypeError):
            return {"error": "invalid document_id"}

        doc = (
            db.query(Document)
            .filter(Document.id == doc_uuid, Document.workspace_id == workspace_id)
            .first()
        )
        if doc is None:
            return {"error": "document not found in this workspace"}

        chunk_filter = (
            Chunk.document_id == doc_uuid,
            Chunk.workspace_id == workspace_id,
        )
        total = db.query(Chunk).filter(*chunk_filter).count()

        start = max(0, int(start_chunk))
        limit = max(1, min(int(max_chunks), 12))
        rows = (
            db.query(Chunk)
            .filter(*chunk_filter)
            .order_by(Chunk.chunk_index)
            .offset(start)
            .limit(limit)
            .all()
        )

        content = "\n\n".join(ch.content or "" for ch in rows)
        content_truncated = len(content) > 12_000
        if content_truncated:
            content = content[:12_000]

        returned = len(rows)
        has_more = start + returned < total
        payload: dict[str, Any] = {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "status": doc.status,
            "total_chunks": total,
            "start_chunk": start,
            "chunks_returned": returned,
            "has_more": has_more,
            "next_start_chunk": start + returned if has_more else None,
            "content": content,
            "content_truncated": content_truncated,
        }
        if doc.status != "ready" and total == 0:
            payload["note"] = f"document not ingested yet (status: {doc.status})"
        return payload

    @tool
    def fetch_url(url: str) -> dict[str, Any]:
        """
        Fetch a public http(s) web page and return its text.
        Use for URLs from web_search results or a URL the user included in
        their goal. Requires get_current_date to have run earlier in this run.
        Only public pages — private/internal addresses are blocked.
        """

        return fetch_url_content(url)

    @tool
    def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
        """
        Search the public web via DuckDuckGo for external context, benchmarks,
        or definitions not found in workspace documents (when policy allows).
        Requires get_current_date to have run earlier in this run — embed the
        returned year/month in the query (never stale years like 2023).
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
        "read_document": read_document,
        "web_search": web_search,
        "fetch_url": fetch_url,
        "create_note": create_note,
        "get_current_date": get_current_date,
    }
    ordered_names = [name for name in GENERAL_TOOL_ORDER if name in tool_names]
    extra = [name for name in tool_names if name not in GENERAL_TOOL_ORDER]
    return [by_name[name] for name in (*ordered_names, *extra) if name in by_name]
