"""Topic study-sheet layout: numbered full-width sections one after another.

Produces presentation_profile ``topic_study_sheet`` from answer sections so
Visual Summary can render teaching boards (Outbox-style study sheets).
"""

from __future__ import annotations

import re
from typing import Any

STUDY_SHEET_PROFILE = "topic_study_sheet"
STUDY_SHEET_MAX_SECTIONS = 12
STUDY_SHEET_MIN_SECTIONS = 4

# Explicit study-sheet / complete-guide intent in the user goal.
_STUDY_SHEET_GOAL = re.compile(
    r"\b("
    r"study\s*sheet|infographic|cheat\s*sheet|one[\s-]?pager|"
    r"complete\s+guide|full\s+guide|deep\s*dive|"
    r"teach\s+me|walk\s+me\s+through|learning\s+arc|"
    r"numbered\s+sections|section[\s-]?by[\s-]?section|"
    r"end[\s-]?to[\s-]?end\s+(?:example|guide|overview)"
    r")\b",
    re.I,
)

# Soft teach intent — only activates study sheet when the answer already has
# enough real sections (avoids hijacking every "explain X").
_TEACH_SOFT = re.compile(
    r"\b(explain|teach|learn|understand|how\s+does|break\s+down)\b",
    re.I,
)

_STRUCTURAL_ONLY = re.compile(
    r"^(overview|summary|introduction|background|conclusion|faq|next\s+steps?|"
    r"key\s+points?|takeaways?|resources?|references?|sources?)\s*$",
    re.I,
)

_NUMBERED_TITLE = re.compile(r"^\s*(\d+)\s*[.):\-–—]\s*(.+)$")


def is_topic_study_sheet_goal(goal: str) -> bool:
    g = (goal or "").strip()
    if not g:
        return False
    return bool(_STUDY_SHEET_GOAL.search(g))


def _real_sections(structured: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading") or "").strip()
        if not heading:
            continue
        bullets = sec.get("bullets") or []
        body = str(sec.get("body") or "").strip()
        has_content = bool(body) or (
            isinstance(bullets, list) and any(str(b).strip() for b in bullets)
        )
        if not has_content:
            continue
        # Drop pure structural shells with almost no content.
        bare = re.sub(r"^\d+\s*[.):\-–—]\s*", "", heading).strip()
        if _STRUCTURAL_ONLY.match(bare) and len(body) < 40 and len(bullets or []) < 2:
            continue
        out.append(sec)
    return out


def should_use_topic_study_sheet(
    *,
    goal: str,
    structured: dict[str, Any],
) -> bool:
    """True when we should build a section-first study-sheet outline."""
    sections = _real_sections(structured)
    if is_topic_study_sheet_goal(goal):
        return len(sections) >= 2
    if _TEACH_SOFT.search(goal or "") and len(sections) >= STUDY_SHEET_MIN_SECTIONS:
        return True
    # Answer already looks like a numbered study board.
    numbered = 0
    for sec in sections:
        h = str(sec.get("heading") or "")
        if _NUMBERED_TITLE.match(h) or re.match(r"^\d+\b", h):
            numbered += 1
    return numbered >= STUDY_SHEET_MIN_SECTIONS


def _section_has_pipe_table(sec: dict[str, Any]) -> bool:
    for b in sec.get("bullets") or []:
        if isinstance(b, str) and b.count("|") >= 1:
            return True
    body = str(sec.get("body") or "")
    pipe_lines = [ln for ln in body.splitlines() if ln.count("|") >= 1]
    return len(pipe_lines) >= 2


def _section_has_numbered_steps(sec: dict[str, Any]) -> bool:
    body = str(sec.get("body") or "")
    if len(re.findall(r"^\s*\d+[.)]\s+\S", body, re.M)) >= 2:
        return True
    bullets = sec.get("bullets") or []
    if isinstance(bullets, list) and len(bullets) >= 3:
        # Long action-ish bullets often map better to steps.
        return bool(
            re.search(
                r"\b(step|begin|commit|insert|update|query|publish|process)\b",
                str(sec.get("heading") or ""),
                re.I,
            )
        )
    return False


def _section_has_arrow_flow(sec: dict[str, Any]) -> bool:
    blob = f"{sec.get('heading') or ''}\n{sec.get('body') or ''}\n"
    for b in sec.get("bullets") or []:
        blob += f"{b}\n"
    arrows = len(re.findall(r"→|->|⇒", blob))
    return arrows >= 2


def infer_section_block_type(sec: dict[str, Any]) -> str:
    """Pick the best GenUI block type for one study-sheet section."""
    heading = str(sec.get("heading") or "")
    body = str(sec.get("body") or "")
    blob = f"{heading}\n{body}".lower()
    bullets = sec.get("bullets") or []
    n_bullets = len(bullets) if isinstance(bullets, list) else 0

    if re.search(r"\b(without|vs\.?|versus|with\s+vs)\b", blob):
        # Dual-path figure when content suggests process risk, else table.
        if _section_has_arrow_flow(sec) or re.search(
            r"\b(lost|fail|risk|outbox|publish|broker)\b", blob
        ):
            return "compare_paths"
        if _section_has_pipe_table(sec) or n_bullets >= 2:
            return "comparison"
    if re.search(r"\b(compar|trade[- ]?off)\b", blob):
        if _section_has_pipe_table(sec) or n_bullets >= 2:
            return "comparison"
    if re.search(r"\b(schema|table|matrix|failure\s+scenar|columns?)\b", blob):
        if _section_has_pipe_table(sec):
            return "table"
    if _section_has_pipe_table(sec) and re.search(
        r"\b(status|scenario|failure|problem|handling|id\b|payload)\b", blob
    ):
        return "table"
    if re.search(
        r"\b(sequence|end[\s-]?to[\s-]?end|request\s+flow|message\s+flow)\b", blob
    ):
        return "sequence_diagram" if _section_has_arrow_flow(sec) else "flow_diagram"
    if re.search(
        r"\b(flow|pipeline|lifecycle|high[\s-]?level|processor|how\s+it\s+works)\b",
        blob,
    ):
        # Numbered bullets count as a process even when body was split into items.
        if (
            _section_has_arrow_flow(sec)
            or _section_has_numbered_steps(sec)
            or n_bullets >= 3
        ):
            return "flow_diagram"
    if re.search(
        r"\b(transaction|steps?|checklist|how\s+to|procedure|boundaries)\b", blob
    ):
        if _section_has_numbered_steps(sec) or n_bullets >= 2:
            return "steps"
    if re.search(r"\b(best\s+practice|when\s+to\s+use|remember|do\s+not|don'?t)\b", blob):
        return "key_points"
    if re.search(r"\b(summary|takeaway|tl;?dr|conclusion)\b", blob):
        if n_bullets >= 2:
            return "key_points"
        return "summary"
    if re.search(r"\b(warning|risk|lost|failure|important)\b", blob) and n_bullets <= 2:
        if body and n_bullets < 2:
            return "callout"
    if _section_has_numbered_steps(sec):
        return "steps"
    if n_bullets >= 2:
        return "key_points"
    if body:
        return "summary"
    return "key_points"


def _display_title(heading: str, index: int) -> str:
    h = (heading or "").strip()
    m = _NUMBERED_TITLE.match(h)
    if m:
        return f"{m.group(1)}. {m.group(2).strip()}"
    if re.match(r"^\d+\b", h):
        return h
    return f"{index}. {h}"


def _source_hint_for_type(btype: str) -> str:
    return {
        "summary": "summary",
        "key_points": "key_points",
        "steps": "ordered_actions",
        "table": "matrix_rows",
        "comparison": "comparisons",
        "flow_diagram": "process_flow",
        "sequence_diagram": "interaction_sequence",
        "compare_paths": "compare_paths",
        "callout": "priority_message",
        "key_terms": "concepts",
        "faq": "faq",
    }.get(btype, "key_points")


def build_topic_study_sheet_plan(
    structured: dict[str, Any],
    *,
    goal: str = "",
) -> dict[str, Any] | None:
    """
    Section-first layout plan: one full-width block per real answer section.

    ``section_index`` is 1-based into ``structured.sections`` (same list
    assemble_block uses), not a filtered re-numbering.

    Returns None when study-sheet mode should not apply.
    """
    if not should_use_topic_study_sheet(goal=goal, structured=structured):
        return None

    raw_sections = [
        s for s in (structured.get("sections") or []) if isinstance(s, dict)
    ]
    # (1-based index into structured.sections, section dict)
    picked: list[tuple[int, dict[str, Any]]] = []
    for i, sec in enumerate(raw_sections, start=1):
        heading = str(sec.get("heading") or "").strip()
        if not heading:
            continue
        bullets = sec.get("bullets") or []
        body = str(sec.get("body") or "").strip()
        has_content = bool(body) or (
            isinstance(bullets, list) and any(str(b).strip() for b in bullets)
        )
        if not has_content:
            continue
        bare = re.sub(r"^\d+\s*[.):\-–—]\s*", "", heading).strip()
        if _STRUCTURAL_ONLY.match(bare) and len(body) < 40 and len(bullets or []) < 2:
            continue
        picked.append((i, sec))
        if len(picked) >= STUDY_SHEET_MAX_SECTIONS:
            break

    if len(picked) < 2:
        return None

    outline: list[dict[str, Any]] = []
    components: list[str] = []
    for panel_n, (sec_idx, sec) in enumerate(picked, start=1):
        btype = infer_section_block_type(sec)
        title = _display_title(
            str(sec.get("heading") or f"Section {panel_n}"), panel_n
        )
        # Teaching boards read better full-width (Outbox-style cards, scannable).
        width = "full"
        entry = {
            "type": btype,
            "title": title[:120],
            "purpose": f"Study sheet panel {panel_n}",
            "source_hint": _source_hint_for_type(btype),
            "width": width,
            # Index into structured.sections for assemble_block lookup.
            "section_index": sec_idx,
            # Display order for chrome (1..N panels).
            "panel_index": panel_n,
            "affordance": "study_sheet_section",
        }
        outline.append(entry)
        if btype not in components:
            components.append(btype)

    return {
        "presentation_profile": STUDY_SHEET_PROFILE,
        "components": components,
        "block_outline": outline,
        "rationale": (
            f"Topic study sheet: {len(outline)} full-width sections in answer order "
            f"(cap {STUDY_SHEET_MAX_SECTIONS})."
        ),
        "ui_intent": {
            "mode": STUDY_SHEET_PROFILE,
            "section_count": len(outline),
            "eligible_affordances": ["study_sheet_section"],
            "block_order": [e["type"] for e in outline],
        },
    }
