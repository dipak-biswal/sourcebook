"""Code-first GenUI block assembly from layout outline + structured content."""

from __future__ import annotations

import re
from typing import Any

from app.agents.gen_ui import FaqItem, GenUIBlock, KeyTerm, _normalize_block_dict


def _str_list(value: Any, *, limit: int = 14) -> list[str]:
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for item in value:
        text = str(item).strip()
        if text and text not in out:
            out.append(text[:400])
        if len(out) >= limit:
            break
    return out


def _pipe_items_from_structured(structured: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ("matrix_rows", "comparisons", "levels", "key_points"):
        for row in structured.get(key) or []:
            if isinstance(row, str) and "|" in row:
                items.append(row.strip()[:400])
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for b in sec.get("bullets") or []:
            if isinstance(b, str) and "|" in b:
                items.append(b.strip()[:400])
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq[:14]


def _steps_from_structured(structured: dict[str, Any]) -> list[str]:
    for key in ("ordered_actions", "learning_path", "design_process", "steps", "update_checklist"):
        items = _str_list(structured.get(key))
        if items:
            return items
    steps: list[str] = []
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading") or "").strip()
        bullets = _str_list(sec.get("bullets"), limit=8)
        if bullets:
            if heading and re.search(r"step|how|guide|checklist|process|design", heading, re.I):
                steps.extend(bullets)
            elif not steps:
                steps.extend(bullets)
        body = str(sec.get("body") or "").strip()
        for line in body.splitlines():
            m = re.match(r"^\s*(?:\d+[.)]|[-•*])\s+(.+)$", line)
            if m:
                steps.append(m.group(1).strip()[:400])
    return _str_list(steps, limit=12)


def _terms_from_structured(structured: dict[str, Any]) -> list[KeyTerm]:
    terms: list[KeyTerm] = []
    for key in ("concepts", "terms"):
        raw = structured.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                term = str(item.get("term") or item.get("name") or "").strip()
                definition = str(
                    item.get("definition")
                    or item.get("design_note")
                    or item.get("body")
                    or ""
                ).strip()
                if term:
                    terms.append(KeyTerm(term=term[:120], definition=definition[:400]))
            elif isinstance(item, str) and "—" in item:
                left, _, right = item.partition("—")
                terms.append(KeyTerm(term=left.strip()[:120], definition=right.strip()[:400]))
            elif isinstance(item, str) and ":" in item:
                left, _, right = item.partition(":")
                terms.append(KeyTerm(term=left.strip()[:120], definition=right.strip()[:400]))
        if terms:
            return terms[:12]
    # Fallback: key_points as term/definition-ish short lines
    for kp in structured.get("key_points") or []:
        text = str(kp).strip()
        if not text or "|" in text:
            continue
        if ":" in text:
            left, _, right = text.partition(":")
            terms.append(KeyTerm(term=left.strip()[:120], definition=right.strip()[:400]))
        else:
            terms.append(KeyTerm(term=text[:80], definition=""))
        if len(terms) >= 8:
            break
    return terms


def _faq_from_structured(structured: dict[str, Any]) -> list[FaqItem]:
    faqs: list[FaqItem] = []
    for item in structured.get("faq") or []:
        if isinstance(item, dict):
            q = str(item.get("question") or "").strip()
            a = str(item.get("answer") or "").strip()
            if q:
                faqs.append(FaqItem(question=q[:300], answer=a[:800]))
    for item in structured.get("misconceptions") or []:
        if isinstance(item, dict):
            q = str(item.get("question") or item.get("myth") or "").strip()
            a = str(item.get("answer") or item.get("correction") or "").strip()
            if q:
                faqs.append(FaqItem(question=q[:300], answer=a[:800]))
    return faqs[:10]


def _callout_body(structured: dict[str, Any]) -> tuple[str, str]:
    if structured_field := structured.get("priority_message"):
        if isinstance(structured_field, dict):
            return (
                str(structured_field.get("title") or "Priority").strip()[:80],
                str(structured_field.get("body") or structured_field.get("text") or "").strip()[:600],
            )
        text = str(structured_field).strip()
        if text:
            return "Priority", text[:600]
    for key in ("gaps", "risks"):
        items = structured.get(key) or []
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                body = str(first.get("body") or first.get("text") or first).strip()
            else:
                body = str(first).strip()
            if body:
                return "Priority", body[:600]
    summary = str(structured.get("summary") or "").strip()
    if summary:
        # First sentence as callout when no explicit priority module
        first = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)[0].strip()
        return "Key takeaway", first[:600]
    return "Priority", ""


def _chips_from_themes(structured: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for t in structured.get("themes") or []:
        label = str(t).strip()
        if not label:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "theme"
        items.append(f"{label}|{slug}")
    return items[:8]


def _levels_items(structured: dict[str, Any]) -> list[str]:
    items = _str_list(structured.get("levels"))
    if items:
        return items
    out: list[str] = []
    for kp in structured.get("key_points") or []:
        if isinstance(kp, str) and "|" in kp and re.search(
            r"strong|growing|gap|foundational|weak", kp, re.I
        ):
            out.append(kp.strip()[:400])
    return out[:10]


def assemble_block(
    outline_entry: dict[str, Any],
    structured: dict[str, Any],
) -> GenUIBlock | None:
    """Map one outline entry + source_hint to a schema-native GenUIBlock."""
    btype = str(outline_entry.get("type") or "").strip()
    title = str(outline_entry.get("title") or "").strip() or None
    hint = str(outline_entry.get("source_hint") or btype).strip()
    tags = outline_entry.get("tags")
    tag_list = [str(t).strip() for t in tags] if isinstance(tags, list) else None

    block: GenUIBlock | None = None

    if btype == "summary" or hint == "summary":
        body = str(structured.get("summary") or "").strip()
        if not body and structured.get("key_points"):
            body = " ".join(_str_list(structured.get("key_points"), limit=3))
        if body:
            block = GenUIBlock(type="summary", title=title or "Overview", body=body[:2000])

    elif btype == "key_points" or hint == "key_points":
        items = _str_list(structured.get("key_points"))
        if not items:
            for sec in structured.get("sections") or []:
                if isinstance(sec, dict):
                    items.extend(_str_list(sec.get("bullets"), limit=6))
            items = _str_list(items)
        if items:
            block = GenUIBlock(type="key_points", title=title or "Key points", items=items)

    elif btype == "key_terms" or hint in ("concepts", "terms"):
        terms = _terms_from_structured(structured)
        if terms:
            block = GenUIBlock(type="key_terms", title=title or "Core concepts", terms=terms)

    elif btype == "steps" or hint in (
        "ordered_actions",
        "learning_path",
        "design_process",
        "steps",
    ):
        items = _steps_from_structured(structured)
        if items:
            block = GenUIBlock(type="steps", title=title or "Steps", items=items)

    elif btype == "table" or hint == "matrix_rows":
        items = _str_list(structured.get("matrix_rows"))
        if not items:
            items = _pipe_items_from_structured(structured)
        if items:
            block = GenUIBlock(type="table", title=title or "Comparison", items=items)

    elif btype == "comparison" or hint == "comparisons":
        items = _str_list(structured.get("comparisons"))
        if not items:
            items = _pipe_items_from_structured(structured)
        if items:
            block = GenUIBlock(type="comparison", title=title or "Tradeoffs", items=items)

    elif btype == "progress" or hint == "levels":
        items = _levels_items(structured)
        if items:
            block = GenUIBlock(type="progress", title=title or "Levels", items=items)

    elif btype == "faq" or hint in ("faq", "misconceptions"):
        faqs = _faq_from_structured(structured)
        if faqs:
            block = GenUIBlock(type="faq", title=title or "FAQ", faqs=faqs)

    elif btype == "callout" or hint == "priority_message":
        ctitle, body = _callout_body(structured)
        if body:
            block = GenUIBlock(
                type="callout",
                title=title or ctitle,
                body=body,
            )

    elif btype == "chips" or hint == "themes":
        items = _chips_from_themes(structured)
        if items:
            block = GenUIBlock(type="chips", title=title or "Themes", items=items)

    elif btype == "timeline" or hint == "milestones":
        items = _str_list(structured.get("milestones") or structured.get("timeline"))
        if not items:
            items = [i for i in _pipe_items_from_structured(structured) if re.search(r"\b(19|20)\d{2}\b", i)]
        if items:
            block = GenUIBlock(type="timeline", title=title or "Timeline", items=items)

    elif btype == "metrics" or hint == "metrics":
        items = _str_list(structured.get("metrics"))
        if items:
            block = GenUIBlock(type="metrics", title=title or "Metrics", items=items)

    if block is None:
        return None
    if tag_list:
        block = block.model_copy(update={"tags": tag_list[:6]})
    # Drop title-only / empty
    norm = _normalize_block_dict(block.model_dump())
    if not norm:
        return None
    try:
        return GenUIBlock.model_validate(norm)
    except Exception:
        return None


def assemble_blocks(
    outline: list[dict[str, Any]] | None,
    structured: dict[str, Any],
) -> tuple[list[GenUIBlock], list[dict[str, str]]]:
    """
    Assemble GenUI blocks from plan outline.

    Returns (blocks, dropped) where dropped has type + reason.
    """
    blocks: list[GenUIBlock] = []
    dropped: list[dict[str, str]] = []
    if not outline:
        return blocks, dropped

    for entry in outline:
        if not isinstance(entry, dict):
            continue
        btype = str(entry.get("type") or "block")
        assembled = assemble_block(entry, structured)
        if assembled is None:
            dropped.append(
                {
                    "type": btype,
                    "reason": f"no data for source_hint={entry.get('source_hint') or btype}",
                }
            )
            continue
        blocks.append(assembled)
        if len(blocks) >= 10:
            break
    return blocks, dropped


def payload_from_assembly(
    *,
    layout_plan: dict[str, Any],
    structured: dict[str, Any],
    goal: str,
    workspace_name: str = "",
    source_files: list[str] | None = None,
) -> dict[str, Any] | None:
    """Build generative_ui dict from code assembly, or None if empty."""
    outline = layout_plan.get("block_outline") or []
    blocks, dropped = assemble_blocks(outline if isinstance(outline, list) else [], structured)
    if not blocks:
        return None

    summary = str(structured.get("summary") or "").strip()
    plain = summary or (blocks[0].body if blocks[0].body else goal[:200])
    title = (
        workspace_name.strip()
        or str(layout_plan.get("presentation_profile") or "Visual summary").replace("_", " ").title()
    )
    if goal and len(goal) < 80:
        title = goal[:80]

    return {
        "type": "generative_ui",
        "title": title[:120],
        "plain_summary": plain[:600],
        "presentation_profile": str(
            layout_plan.get("presentation_profile") or "workspace_derived"
        ),
        "blocks": [b.model_dump() for b in blocks],
        "source_files": list(source_files or []),
        "assembly_meta": {
            "assembled_blocks": [b.type for b in blocks],
            "dropped_blocks": dropped,
            "render_fallback_used": False,
        },
    }
