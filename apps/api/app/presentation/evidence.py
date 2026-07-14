"""Collect agent tool evidence for the presentation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentEvidenceHit:
    filename: str
    snippet: str
    score: float | None = None
    chunk_id: str | None = None


@dataclass
class WebEvidenceHit:
    title: str
    snippet: str
    url: str = ""


@dataclass
class AgentEvidenceBundle:
    document_hits: list[DocumentEvidenceHit] = field(default_factory=list)
    web_hits: list[WebEvidenceHit] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(self.document_hits or self.web_hits)


def _parse_document_hits(output: Any) -> list[DocumentEvidenceHit]:
    if not isinstance(output, list):
        return []
    hits: list[DocumentEvidenceHit] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        snippet = (item.get("snippet") or "").strip()
        if not snippet:
            continue
        filename = (item.get("filename") or "document").strip() or "document"
        score = item.get("score")
        chunk_id = item.get("chunk_id")
        hits.append(
            DocumentEvidenceHit(
                filename=filename,
                snippet=snippet[:600],
                score=float(score) if isinstance(score, (int, float)) else None,
                chunk_id=str(chunk_id) if chunk_id else None,
            )
        )
    return hits


def _parse_web_hits(output: Any) -> list[WebEvidenceHit]:
    if not isinstance(output, dict):
        return []
    results = output.get("results")
    if not isinstance(results, list):
        return []
    hits: list[WebEvidenceHit] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        url = (item.get("url") or "").strip()
        if not title and not snippet:
            continue
        hits.append(
            WebEvidenceHit(
                title=title or url or "Web result",
                snippet=snippet[:600],
                url=url,
            )
        )
    return hits


def collect_evidence_from_steps(
    steps: list[Any],
    *,
    max_document_hits: int = 12,
    max_web_hits: int = 8,
) -> AgentEvidenceBundle:
    """
    Flatten search_documents and web_search tool_result steps into one bundle.
    Accepts AgentStep ORM objects or step dicts from tests.
    """
    doc_hits: list[DocumentEvidenceHit] = []
    web_hits: list[WebEvidenceHit] = []
    seen_doc: set[str] = set()
    seen_web: set[str] = set()

    for step in sorted(steps, key=lambda s: _step_index(s)):
        if _step_type(step) != "tool_result":
            continue
        tool_name = _step_tool_name(step)
        output = _step_output(step)
        if tool_name == "search_documents":
            for hit in _parse_document_hits(output):
                key = hit.chunk_id or f"{hit.filename}:{hit.snippet[:120]}"
                if key in seen_doc:
                    continue
                seen_doc.add(key)
                doc_hits.append(hit)
                if len(doc_hits) >= max_document_hits:
                    break
        elif tool_name == "web_search":
            for hit in _parse_web_hits(output):
                key = hit.url or f"{hit.title}:{hit.snippet[:120]}"
                if key in seen_web:
                    continue
                seen_web.add(key)
                web_hits.append(hit)
                if len(web_hits) >= max_web_hits:
                    break

    return AgentEvidenceBundle(document_hits=doc_hits, web_hits=web_hits)


def serialize_agent_evidence(bundle: AgentEvidenceBundle) -> dict[str, list[dict[str, Any]]]:
    return {
        "document_hits": [
            {
                "filename": hit.filename,
                "snippet": hit.snippet,
                "score": hit.score,
                "chunk_id": hit.chunk_id,
            }
            for hit in bundle.document_hits
        ],
        "web_hits": [
            {
                "title": hit.title,
                "snippet": hit.snippet,
                "url": hit.url,
            }
            for hit in bundle.web_hits
        ],
    }


def format_agent_evidence(bundle: AgentEvidenceBundle) -> str:
    """Prompt + grounding text for evidence the agent already retrieved."""
    if not bundle.has_content():
        return ""

    parts: list[str] = [
        "AGENT TOOL EVIDENCE (same sources the Answer tab used — prefer over re-inferred facts):"
    ]
    if bundle.document_hits:
        parts.append("Workspace search hits:")
        for i, hit in enumerate(bundle.document_hits, start=1):
            score = f", score={hit.score:.3f}" if hit.score is not None else ""
            parts.append(f"[doc-{i}] ({hit.filename}{score})\n{hit.snippet}")
    if bundle.web_hits:
        parts.append("Web search hits:")
        for i, hit in enumerate(bundle.web_hits, start=1):
            src = f" ({hit.url})" if hit.url else ""
            parts.append(f"[web-{i}] {hit.title}{src}\n{hit.snippet}")

    return "\n\n".join(parts)


def _step_index(step: Any) -> int:
    if isinstance(step, dict):
        return int(step.get("step_index") or 0)
    return int(getattr(step, "step_index", 0) or 0)


def _step_type(step: Any) -> str:
    if isinstance(step, dict):
        return str(step.get("type") or "")
    return str(getattr(step, "type", "") or "")


def _step_tool_name(step: Any) -> str:
    if isinstance(step, dict):
        return str(step.get("tool_name") or "")
    return str(getattr(step, "tool_name", "") or "")


def _step_output(step: Any) -> Any:
    if isinstance(step, dict):
        return step.get("output")
    return getattr(step, "output", None)