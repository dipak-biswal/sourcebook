"""Extract compact structured content from main-agent answers for visual planning."""

from __future__ import annotations

import json
import re
from typing import Any

from app.presentation.evidence import AgentEvidenceBundle
from app.presentation.ui_intent import available_source_hints

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


def _clean_inline_md(text: str) -> str:
    """Strip bold markers and leading bullet/number prefixes from one line."""
    cleaned = re.sub(r"\*\*", "", text or "").strip()
    cleaned = re.sub(r"^(?:[-•*]|\d+[.)])\s+", "", cleaned)
    return cleaned.strip()


# Section headings that describe answer structure, not document topics.
# These must not leak into themes/chips ("Steps / Checklist", "Next Steps"…).
_STRUCTURAL_HEADING_WORDS = frozenset(
    {
        "overview", "summary", "introduction", "background", "conclusion",
        "next", "step", "steps", "checklist", "faq", "faqs", "self", "check",
        "key", "points", "point", "highlights", "takeaways", "recommendations",
        "recommendation", "action", "actions", "items", "resources",
        "references", "sources", "guide", "tips", "notes",
    }
)


def _is_structural_heading(title: str) -> bool:
    words = re.findall(r"[a-z]+", (title or "").lower())
    return bool(words) and all(w in _STRUCTURAL_HEADING_WORDS for w in words)


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
        chunk_lines = [
            _clean_inline_md(ln) for ln in chunk.splitlines() if ln.strip()
        ]
        chunk_lines = [ln for ln in chunk_lines if ln]
        if len(chunk_lines) < 2:
            continue
        head = chunk_lines[0]
        rest = chunk_lines[1:]
        if head.endswith("?"):
            # A question followed only by more questions is a self-check
            # checklist, not a Q&A pair — don't fabricate an answer from it.
            if all(ln.endswith("?") for ln in rest):
                continue
            faq.append(
                {
                    "question": head[:300],
                    "answer": " ".join(rest)[:800],
                }
            )
        if len(faq) >= _MAX_FAQ:
            break
    return faq


_MAX_STEPS = 12
_STEP_SECTION_HEADING = re.compile(
    r"step|checklist|process|guide|how|plan|workflow", re.I
)


def _extract_numbered_steps(body: str) -> list[str]:
    """
    Turn a numbered list into ordered steps, keeping item structure.

    "1. **Tailor Your Resume**:\n   - Review the job description." becomes
    "Tailor Your Resume — Review the job description." instead of a flat
    mix of labels and sub-bullets.
    """
    steps: list[tuple[str, list[str]]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if numbered:
            steps.append((numbered.group(1).strip(), []))
            continue
        bullet = re.match(r"^[-•*]\s+(.+)$", line)
        if bullet and steps:
            steps[-1][1].append(bullet.group(1).strip())
    if len(steps) < 3:
        return []
    out: list[str] = []
    for label_raw, details in steps[:_MAX_STEPS]:
        label = _clean_inline_md(label_raw).rstrip(":").strip()
        if not label:
            continue
        detail = _clean_inline_md(details[0]) if details else ""
        if detail and len(label) <= 80:
            out.append(f"{label} — {detail}"[:240])
        else:
            out.append(label[:240])
    return out


def _extract_ordered_actions(
    text: str, sections_raw: list[tuple[str, str]]
) -> list[str]:
    """Prefer numbered steps from a step-like section, then the whole answer."""
    for title, body in sections_raw:
        if _STEP_SECTION_HEADING.search(title):
            steps = _extract_numbered_steps(body)
            if steps:
                return steps
    return _extract_numbered_steps(text)


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
        # A paragraph ending in a colon is a lead-in to a list, not a summary.
        if cleaned.endswith(":"):
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
            "ordered_actions": [],
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
            extracted = _extract_faq(body)
            if extracted:
                faq.extend(extracted)
                continue
            # No real Q&A pairs (e.g. a self-check question list):
            # fall through and keep it as a plain section instead.
        if _looks_like_padding(body):
            bullets = _extract_bullets(body, limit=4)
            if bullets:
                key_points.extend(bullets)
            continue
        bullets = _extract_bullets(body, limit=8)
        entry: dict[str, Any] = {"heading": title[:120]}
        if bullets:
            entry["bullets"] = bullets
            if not _is_structural_heading(title) and title.lower() not in {
                t.lower() for t in themes
            }:
                themes.append(title[:60])
        else:
            entry["body"] = body[:_MAX_SECTION_BODY]
        sections.append(entry)

    ordered_actions = _extract_ordered_actions(text, sections_raw)

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

    if not summary:
        # An "Overview"/"Summary" section body is the real summary when the
        # preamble was only a colon lead-in ("Here's a guide…:").
        for entry in sections:
            heading = str(entry.get("heading") or "")
            body = str(entry.get("body") or "").strip()
            if body and re.search(
                r"^(overview|summary|introduction|tl;?dr|about)\b", heading, re.I
            ):
                summary = body[:_MAX_SUMMARY_CHARS]
                break
    if not summary:
        for entry in sections:
            body = str(entry.get("body") or "").strip()
            if body and not _looks_like_padding(body):
                summary = body[:_MAX_SUMMARY_CHARS]
                break
    if not summary and key_points:
        # Never surface a single bullet as "the summary" — it reads as a
        # non-sequitur ("Review the job description carefully.").
        summary = " ".join(key_points[:3])[:_MAX_SUMMARY_CHARS]

    return {
        "summary": summary,
        "key_points": key_points,
        "faq": faq[:_MAX_FAQ],
        "ordered_actions": ordered_actions,
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
    available_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Structured payload passed to the layout planner LLM."""
    if available_fields is None:
        available_fields = sorted(available_source_hints(structured_content or {}))
    return {
        "user_goal": (goal or "").strip(),
        "requested_components": components,
        "structured_content": structured_content,
        "available_source_hints": list(available_fields),
        "evidence_summary": summarize_agent_evidence(evidence),
        "planner_notes": (notes or "").strip() or None,
    }


_PLANNER_FEW_SHOTS: dict[str, str] = {
    "resume_dashboard": (
        'EXAMPLE (resume_dashboard):\n'
        '{"presentation_profile":"resume_dashboard","components":["table","progress","key_points"],'
        '"block_outline":['
        '{"type":"summary","title":"Overview","source_hint":"summary","width":"full","purpose":"Role fit summary"},'
        '{"type":"table","title":"Skills matrix","source_hint":"matrix_rows","width":"full","purpose":"Skills vs role requirements"},'
        '{"type":"progress","title":"Skill levels","source_hint":"levels","width":"half","purpose":"Qualitative skill strength"}'
        '],'
        '"rationale":"Table and progress for resume scan; key_points for highlights."}'
    ),
    "gap_analysis": (
        'EXAMPLE (gap_analysis):\n'
        '{"presentation_profile":"gap_analysis","components":["callout","table","faq"],'
        '"block_outline":['
        '{"type":"callout","title":"Main gap","source_hint":"priority_message","width":"half","purpose":"Primary role gap"},'
        '{"type":"table","title":"Requirements vs evidence","source_hint":"matrix_rows","width":"full","purpose":"Gap comparison rows"},'
        '{"type":"faq","title":"FAQ","source_hint":"faq","width":"half","purpose":"Common questions from answer"}'
        '],'
        '"rationale":"Callout surfaces the main gap; table compares requirements."}'
    ),
    "faq_guide": (
        'EXAMPLE (faq_guide):\n'
        '{"presentation_profile":"faq_guide","components":["summary","faq","key_points"],'
        '"block_outline":['
        '{"type":"summary","title":"Overview","source_hint":"summary","width":"full","purpose":"Short overview"},'
        '{"type":"faq","title":"FAQ","source_hint":"faq","width":"half","purpose":"Question and answer pairs"},'
        '{"type":"key_points","title":"Highlights","source_hint":"key_points","width":"half","purpose":"Top bullets"}'
        '],'
        '"rationale":"FAQ-first layout when the answer is Q&A heavy."}'
    ),
    "mechanism_explainer": (
        'EXAMPLE (mechanism_explainer):\n'
        '{"presentation_profile":"mechanism_explainer","components":'
        '["summary","flow_diagram","sequence_diagram"],'
        '"block_outline":['
        '{"type":"summary","title":"Overview","source_hint":"summary","width":"full",'
        '"purpose":"What the mechanism is in plain language"},'
        '{"type":"flow_diagram","title":"How it works","source_hint":"process_flow",'
        '"width":"full","purpose":"Architecture: components and handoffs"},'
        '{"type":"sequence_diagram","title":"Worked example","source_hint":'
        '"interaction_sequence","width":"full",'
        '"purpose":"Step-by-step walkthrough of one concrete run"}'
        '],'
        '"rationale":"Explain goals are teaching visuals: overview + flow + worked example only — no FAQ/steps/key_points."}'
    ),
}

# One-line purpose for each planner block type (menu for the LLM).
_BLOCK_MENU: dict[str, str] = {
    "summary": "short prose overview",
    "key_points": "bullet highlights",
    "key_terms": "term + definition glossary",
    "steps": "ordered how-to / process",
    "table": "multi-column comparison matrix",
    "comparison": "side-by-side tradeoffs",
    "progress": "qualitative levels (Strong/Growing/Gap)",
    "faq": "Q&A pairs",
    "callout": "priority alert / gap / risk",
    "chips": "theme filters (≥2 themes)",
    "timeline": "dated milestones",
    "metrics": "label | value stats",
    "flow_diagram": "boxes/arrows diagram of a process or mechanism (only when the answer explains how something works step-by-step)",
    "sequence_diagram": "lifeline diagram of ordered interactions between named actors (only for multi-actor/protocol/event-flow explanations)",
}

_SOURCE_HINT_BLOCK_TYPE: dict[str, str] = {
    "summary": "summary",
    "key_points": "key_points",
    "concepts": "key_terms",
    "ordered_actions": "steps",
    "matrix_rows": "table",
    "comparisons": "comparison",
    "levels": "progress",
    "faq": "faq",
    "priority_message": "callout",
    "themes": "chips",
    "milestones": "timeline",
    "metrics": "metrics",
    "process_flow": "flow_diagram",
    "interaction_sequence": "sequence_diagram",
}


def _planner_few_shot(goal: str, components: list[str]) -> str:
    goal_l = (goal or "").lower()
    if any(c in components for c in ("flow_diagram", "sequence_diagram")) or re.search(
        r"\b(explain|how does|how it works|mechanism|lifecycle|under the hood|"
        r"what happens when|event loop|pipeline)\b",
        goal_l,
    ):
        return _PLANNER_FEW_SHOTS["mechanism_explainer"]
    if "faq" in components or re.search(r"\bfaq\b", goal_l):
        return _PLANNER_FEW_SHOTS["faq_guide"]
    if any(c in components for c in ("progress", "table", "chart")) or re.search(
        r"resume|cv|role|gap", goal_l
    ):
        if re.search(r"gap|compare|vs\b", goal_l):
            return _PLANNER_FEW_SHOTS["gap_analysis"]
        return _PLANNER_FEW_SHOTS["resume_dashboard"]
    return _PLANNER_FEW_SHOTS["faq_guide"]


def _format_available_fields_block(available: list[str]) -> str:
    """Prompt section listing only present source_hints."""
    if not available:
        return (
            "AVAILABLE SOURCE FIELDS (use only these source_hint values; each maps to real data):\n"
            "  (none — structured content is thin; prefer a minimal summary/key_points plan if any data exists)\n"
        )
    lines = [
        "AVAILABLE SOURCE FIELDS (use only these source_hint values; each maps to real data):"
    ]
    for hint in available:
        btype = _SOURCE_HINT_BLOCK_TYPE.get(hint, hint)
        purpose = _BLOCK_MENU.get(btype, "")
        suffix = f" → {btype}" + (f" ({purpose})" if purpose else "")
        lines.append(f"  - {hint}{suffix}  (present)")
    lines.append("  # everything else is EMPTY — do not plan a block for it.")
    return "\n".join(lines) + "\n"


def _format_block_menu() -> str:
    lines = ["BLOCK MENU (type purpose — pick types that match an available source_hint):"]
    for btype, purpose in _BLOCK_MENU.items():
        lines.append(f"  - {btype}: {purpose}")
    return "\n".join(lines) + "\n"


def format_plan_layout_prompt(
    payload: dict[str, Any],
    *,
    layout_hints: str,
    workspace_example: dict[str, Any] | None = None,
) -> str:
    """Compact planner prompt — structured JSON in, layout JSON out."""
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    goal = str(payload.get("user_goal") or "")
    components = list(payload.get("requested_components") or [])
    if isinstance(workspace_example, dict) and workspace_example.get("block_outline"):
        profile = str(
            workspace_example.get("presentation_profile") or "workspace_layout"
        )
        few_shot = (
            f"EXAMPLE ({profile} — ideal layout for this workspace's domain):\n"
            f"{json.dumps(workspace_example, ensure_ascii=False)}"
        )
    else:
        few_shot = _planner_few_shot(goal, components)
    planner_notes = payload.get("planner_notes")
    notes_block = ""
    if planner_notes:
        notes_block = f"\nPLANNER NOTES (address these):\n{planner_notes}\n"
    available = list(payload.get("available_source_hints") or [])
    if not available and isinstance(payload.get("structured_content"), dict):
        available = sorted(available_source_hints(payload["structured_content"]))
    available_block = _format_available_fields_block(available)
    menu_block = _format_block_menu()
    return (
        "You are the Visual Summary layout planner.\n"
        "Input is STRUCTURED CONTENT extracted from the main workspace agent's answer.\n"
        "You decide which blocks to show, their order, titles, and width.\n"
        "Do not invent facts. Omit blocks when the source field is empty.\n\n"
        f"{few_shot}\n\n"
        f"{available_block}\n"
        f"{menu_block}\n"
        f"STRUCTURED INPUT:\n{body}\n"
        f"{notes_block}\n"
        f"{layout_hints}\n\n"
        "RULES:\n"
        "- Lead with the block that best answers the user's goal.\n"
        '- Choose width per block: "full" for wide data '
        "(table/comparison/timeline/steps/chips/summary),\n"
        '  "half" for compact blocks that should sit side-by-side '
        "(key_points/faq/key_terms/callout/metrics/progress).\n"
        "- Group related blocks next to each other. Prefer 4-7 blocks; "
        "omit anything without data.\n"
        "- Every block_outline entry MUST include type, title, source_hint, and width.\n"
        "- Use only source_hint values listed under AVAILABLE SOURCE FIELDS.\n"
        "- Only plan flow_diagram when the answer describes a mechanism/pipeline with "
        "distinct steps that hand off to each other; only plan sequence_diagram for an "
        "ordered, multi-actor interaction. Every diagram node id used in an edge must "
        "exist in nodes. These are a visual restatement of what you already said, not "
        "new research — do not invent actors or steps.\n\n"
        "OUTPUT (JSON only):\n"
        "{\n"
        '  "presentation_profile": "real id like gap_analysis or mechanism_explainer '
        '(never the placeholder short_snake_case)",\n'
        '  "components": ["table", "progress", ...],\n'
        '  "block_outline": [\n'
        '    {"type": "table", "title": "...", "source_hint": "matrix_rows", '
        '"width": "full", "purpose": "what facts this block shows"}\n'
        "  ],\n"
        '  "rationale": "1-3 sentences on layout choices"\n'
        "}\n"
        "Use only grounded components. Omit blocks when structured data is missing."
    )


_FIELD_SHAPE_HINTS: dict[str, str] = {
    "summary": "type summary — title optional, body = 2-4 sentences from structured summary",
    "key_points": "type key_points — items = string bullets from structured key_points",
    "faq": 'type faq — faqs = [{"question":"","answer":""}] from structured faq',
    "key_terms": 'type key_terms — terms = [{"term":"","definition":""}]',
    "table": "type table — items = pipe rows e.g. Col1 | Col2 (never use a data field)",
    "progress": "type progress — items = Label | Strong/Growing/Gap (never use a data field)",
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
        "- Return ONLY valid JSON (no markdown fences).\n"
        "- Each block uses items (string[]), body, faqs, or terms — never a data field.\n"
        "- Use plain text in cells and labels — no markdown (no **bold**, bullets, or 1. numbering).\n"
        "{\n"
        '  "title": "short title",\n'
        '  "plain_summary": "2-4 sentences from structured summary",\n'
        f'  "presentation_profile": "{profile}",\n'
        '  "blocks": [{"type":"table","title":"...","items":["Col1 | Col2","a | b"]}]\n'
        "}\n"
    )