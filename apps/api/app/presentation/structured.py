"""Extract compact structured content from main-agent answers for visual planning."""

from __future__ import annotations

import json
import re
from typing import Any

from app.presentation.evidence import AgentEvidenceBundle

_MAX_SUMMARY_CHARS = 600
_MAX_SECTION_BODY = 1200
_MAX_BULLETS = 14
_MAX_FAQ = 10
_MAX_EVIDENCE_SNIPPETS = 6
_MAX_SNIPPET_CHARS = 280

_HEADING = re.compile(
    r"^(?:"
    r"#{1,4}\s+(.+)|"
    r"\*\*(?!Q:|A:|Question:|Answer:)(.+?)\*\*|"
    r"[•*]?\s*([A-Z][A-Za-z0-9 /&'’\-]{2,48}):?\s*"
    r")$",
    re.M,
)
_BULLET = re.compile(r"^[\s]*(?:[-•*]|\d+[.)])\s+(.+)$", re.M)
_FAQ_Q = re.compile(
    r"^(?:\*\*)?(?:Q(?:uestion)?[:\s]+|FAQ[:\s]+)(.+?)(?:\*\*)?\s*$",
    re.I | re.M,
)
_FAQ_A = re.compile(r"^(?:\*\*)?(?:A(?:nswer)?[:\s]+)(.+?)(?:\*\*)?\s*$", re.I | re.M)


def _normalize_heading(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().strip(":"))


def _is_faq_heading(title: str) -> bool:
    return bool(re.search(r"\bfaq\b|frequently asked", title, re.I))


def _is_key_points_heading(title: str) -> bool:
    return bool(
        re.search(
            r"key\s*points?|highlights?|takeaways?|main\s*themes?|summary\s*points?",
            title,
            re.I,
        )
    )


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        title = _normalize_heading(
            next(g for g in match.groups() if g) if match.groups() else ""
        )
        if not title:
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def _extract_bullets(block: str, *, limit: int = _MAX_BULLETS) -> list[str]:
    items: list[str] = []
    for match in _BULLET.finditer(block):
        line = match.group(1).strip()
        if line and line not in items:
            items.append(line[:400])
        if len(items) >= limit:
            break
    return items


_Q_NUMBERED_HEADING = re.compile(r"^Q\d+\s*:\s*", re.I)
_LABEL_ONLY_BULLET = re.compile(r"^\*\*.+\*\*:?\s*$")


def _promote_question_sections_to_faq(
    sections: list[dict[str, Any]],
    faq: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Turn Q1:/question headings in sections into faq entries for render."""
    seen = {f"{item['question']}|{item['answer']}" for item in faq}
    for entry in sections:
        heading = str(entry.get("heading") or "").strip()
        if not heading:
            continue
        is_question = heading.endswith("?") or bool(_Q_NUMBERED_HEADING.match(heading))
        if not is_question:
            continue
        question = _Q_NUMBERED_HEADING.sub("", heading).strip()
        answer = " ".join(entry.get("bullets") or [])
        if not answer:
            answer = str(entry.get("body") or "").strip()
        if not question or not answer:
            continue
        key = f"{question}|{answer}"
        if key in seen:
            continue
        seen.add(key)
        faq.append({"question": question[:300], "answer": answer[:800]})
    return faq


def _clean_key_point_bullets(key_points: list[str]) -> list[str]:
    """Drop section labels mistaken as bullets (e.g. '**Professional Summary**:')."""
    cleaned: list[str] = []
    for item in key_points:
        text = item.strip()
        if not text or _LABEL_ONLY_BULLET.match(text):
            continue
        cleaned.append(text)
    return cleaned


def _extract_faq(block: str) -> list[dict[str, str]]:
    faq: list[dict[str, str]] = []
    lines = block.splitlines()
    i = 0
    while i < len(lines) and len(faq) < _MAX_FAQ:
        line = lines[i].strip()
        q_match = _FAQ_Q.match(line)
        if q_match:
            question = q_match.group(1).strip().strip("*")
            answer = ""
            if i + 1 < len(lines):
                a_match = _FAQ_A.match(lines[i + 1].strip())
                if a_match:
                    answer = a_match.group(1).strip()
                    i += 1
            if question:
                faq.append({"question": question[:300], "answer": answer[:800]})
        i += 1
    if faq:
        return faq

    # Paragraph pairs: bold question line followed by answer paragraph
    chunks = re.split(r"\n\s*\n", block)
    for chunk in chunks:
        chunk_lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        if len(chunk_lines) < 2:
            continue
        head = chunk_lines[0].strip("*").strip()
        if head.endswith("?"):
            faq.append(
                {
                    "question": head[:300],
                    "answer": " ".join(chunk_lines[1:])[:800],
                }
            )
        if len(faq) >= _MAX_FAQ:
            break
    return faq


def _looks_like_padding(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 40:
        return False
    unique = set(stripped.split())
    if len(unique) <= 2 and len(stripped) > 200:
        return True
    if len(stripped) > 200 and stripped.count(stripped[0]) / len(stripped) > 0.8:
        return True
    return False


def _first_summary_paragraph(text: str) -> str:
    for chunk in re.split(r"\n\s*\n", text):
        cleaned = chunk.strip()
        if not cleaned:
            continue
        if cleaned.startswith(("#", "-", "•", "*")):
            continue
        if _HEADING.match(cleaned):
            continue
        if _looks_like_padding(cleaned):
            continue
        return cleaned[:_MAX_SUMMARY_CHARS]
    return ""


def extract_structured_content(answer: str, *, goal: str = "") -> dict[str, Any]:
    """
    Parse the main agent's narrative into compact sections for layout planning.

    Returns JSON-serializable facts — not the raw answer blob.
    """
    text = (answer or "").strip()
    if not text:
        return {
            "summary": "",
            "key_points": [],
            "faq": [],
            "sections": [],
            "themes": [],
        }

    sections_raw = _split_sections(text)
    key_points: list[str] = []
    faq: list[dict[str, str]] = []
    sections: list[dict[str, Any]] = []
    themes: list[str] = []

    heading_matches = list(_HEADING.finditer(text))
    if heading_matches:
        preamble = text[: heading_matches[0].start()].strip()
    else:
        preamble = text

    summary = _first_summary_paragraph(preamble or text)

    for title, body in sections_raw:
        if _is_key_points_heading(title):
            key_points.extend(_extract_bullets(body))
            continue
        if _is_faq_heading(title):
            faq.extend(_extract_faq(body))
            continue
        if _looks_like_padding(body):
            bullets = _extract_bullets(body, limit=4)
            if bullets:
                key_points.extend(bullets)
            continue
        bullets = _extract_bullets(body, limit=8)
        entry: dict[str, Any] = {"heading": title[:120]}
        if bullets:
            entry["bullets"] = bullets
            if title.lower() not in {t.lower() for t in themes}:
                themes.append(title[:60])
        else:
            entry["body"] = body[:_MAX_SECTION_BODY]
        sections.append(entry)

    if not key_points:
        key_points = _extract_bullets(text)

    if not faq and re.search(r"\bfaq\b", goal, re.I):
        for title, body in sections_raw:
            if _is_faq_heading(title):
                continue
            faq.extend(_extract_faq(body))

    # De-dupe key points while preserving order
    seen: set[str] = set()
    deduped_kp: list[str] = []
    for item in key_points:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_kp.append(item)
    key_points = _clean_key_point_bullets(deduped_kp[:_MAX_BULLETS])
    faq = _promote_question_sections_to_faq(sections, faq)

    if not summary and key_points:
        summary = key_points[0][:_MAX_SUMMARY_CHARS]

    return {
        "summary": summary,
        "key_points": key_points,
        "faq": faq[:_MAX_FAQ],
        "sections": sections[:8],
        "themes": themes[:6],
    }


def summarize_agent_evidence(bundle: AgentEvidenceBundle) -> dict[str, Any]:
    """Compact evidence for planners — not full snippet dumps."""
    doc_snippets: list[dict[str, str]] = []
    for hit in bundle.document_hits[:_MAX_EVIDENCE_SNIPPETS]:
        doc_snippets.append(
            {
                "filename": hit.filename,
                "snippet": hit.snippet[:_MAX_SNIPPET_CHARS],
            }
        )
    web_snippets: list[dict[str, str]] = []
    for hit in bundle.web_hits[:4]:
        web_snippets.append(
            {
                "title": hit.title[:120],
                "snippet": hit.snippet[:_MAX_SNIPPET_CHARS],
                "url": hit.url[:200],
            }
        )
    return {
        "document_snippets": doc_snippets,
        "web_snippets": web_snippets,
        "document_hit_count": len(bundle.document_hits),
        "web_hit_count": len(bundle.web_hits),
    }


def build_plan_layout_input(
    *,
    goal: str,
    structured_content: dict[str, Any],
    evidence: AgentEvidenceBundle,
    components: list[str],
    notes: str = "",
) -> dict[str, Any]:
    """Structured payload passed to the layout planner LLM."""
    return {
        "user_goal": (goal or "").strip(),
        "requested_components": components,
        "structured_content": structured_content,
        "evidence_summary": summarize_agent_evidence(evidence),
        "planner_notes": (notes or "").strip() or None,
    }


def format_plan_layout_prompt(payload: dict[str, Any], *, layout_hints: str) -> str:
    """Compact planner prompt — structured JSON in, layout JSON out."""
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "You are the Visual Summary layout planner.\n"
        "Input is STRUCTURED CONTENT extracted from the main workspace agent's answer.\n"
        "Do not invent facts. Plan UI blocks that present the structured content.\n\n"
        f"STRUCTURED INPUT:\n{body}\n\n"
        f"{layout_hints}\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "presentation_profile": "short_snake_case e.g. resume_dashboard",\n'
        '  "components": ["table", "progress", ...],\n'
        '  "block_outline": [\n'
        '    {"type": "table", "title": "...", "purpose": "what facts this block shows"}\n'
        "  ],\n"
        '  "rationale": "1-3 sentences on layout choices"\n'
        "}\n"
        "Use only grounded components. Omit blocks when structured data is missing."
    )


def format_render_content_payload(structured_content: dict[str, Any]) -> str:
    """Serialize structured facts for the render engine (not the raw answer)."""
    return json.dumps(structured_content, ensure_ascii=False, indent=2)


_FIELD_SHAPE_HINTS: dict[str, str] = {
    "summary": "type summary — title optional, body = 2-4 sentences from structured summary",
    "key_points": "type key_points — items = string bullets from structured key_points",
    "faq": 'type faq — faqs = [{"question":"","answer":""}] from structured faq',
    "key_terms": 'type key_terms — terms = [{"term":"","definition":""}]',
    "table": "type table — items = pipe rows e.g. Col1 | Col2",
    "progress": "type progress — items = Label | Strong/Growing/Gap (qualitative only)",
    "chart": "type chart — items = Label | level (qualitative)",
    "chips": 'type chips — items = "Label|slug"; optional tags on other blocks',
    "callout": "type callout — body required, short title",
    "steps": "type steps — ordered items list",
    "timeline": "type timeline — items = Period | Title | Detail (only if dates in facts)",
    "comparison": "type comparison — items = Aspect | A | B",
    "quote": "type quote — body = quote text",
    "metrics": "type metrics — items = Label | Value",
}


def format_render_engine_prompt(
    *,
    layout_plan: dict[str, Any],
    structured_content: dict[str, Any],
    evidence_summary: dict[str, Any],
    workspace_name: str = "",
) -> str:
    """
    Slim render-engine prompt: execute the approved plan using structured facts only.
    No user goal, workspace essay, or RAG excerpt dump.
    """
    components = list(layout_plan.get("components") or [])
    profile = str(layout_plan.get("presentation_profile") or "general_summary")
    outline = layout_plan.get("block_outline") or []
    shape_lines = [
        f"  - {_FIELD_SHAPE_HINTS[c]}"
        for c in components
        if c in _FIELD_SHAPE_HINTS
    ]
    shapes = "\n".join(shape_lines) if shape_lines else "  - Use block types from block_outline"

    return (
        "You are the VISUAL SUMMARY render engine.\n"
        "Execute the APPROVED LAYOUT PLAN below — populate UI blocks from STRUCTURED CONTENT.\n"
        "Do NOT re-analyze documents, repeat the user goal, or add block types not in the plan.\n\n"
        f"WORKSPACE: {workspace_name.strip() or '(unnamed)'}\n\n"
        "APPROVED LAYOUT PLAN:\n"
        f"{json.dumps(layout_plan, ensure_ascii=False, indent=2)}\n\n"
        "STRUCTURED CONTENT (facts — map into block_outline; do not invent):\n"
        f"{json.dumps(structured_content, ensure_ascii=False, indent=2)}\n\n"
        "EVIDENCE SUMMARY (use only if a fact is missing from structured content):\n"
        f"{json.dumps(evidence_summary, ensure_ascii=False, indent=2)}\n\n"
        "BLOCK SHAPES FOR THIS PLAN:\n"
        f"{shapes}\n\n"
        "RULES:\n"
        f"- Output presentation_profile: {profile}\n"
        f"- Emit exactly the block types in components: {components or ['from block_outline']}\n"
        f"- One block per block_outline entry ({len(outline)} planned) when outline is non-empty.\n"
        "- Prefer structured_content.faq for faq blocks; use sections with Q headings if faq is empty.\n"
        "- Never invent employers, metrics, or dates not present in structured content or evidence.\n"
        "- Return ONLY valid JSON (no markdown fences):\n"
        "{\n"
        '  "title": "short title",\n'
        '  "plain_summary": "2-4 sentences from structured summary",\n'
        f'  "presentation_profile": "{profile}",\n'
        '  "blocks": [...]\n'
        "}\n"
    )