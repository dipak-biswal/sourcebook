"""Code-first GenUI block assembly from layout outline + structured content."""

from __future__ import annotations

import re
from typing import Any

from app.visual_summary.blocks.gen_ui import (
    DiagramEdge,
    DiagramNode,
    FaqItem,
    GenUIBlock,
    KeyTerm,
    SequenceMessage,
    _normalize_block_dict,
)
from app.visual_summary.blocks.registry import FULL_WIDTH_TYPES, WIDTH_PROMOTE_TYPES


# Width policy comes from the block registry: wide blocks carry more data and
# read better full-width; "promote" blocks pair up until they hold many rows.
_FULL_WIDTH_TYPES = FULL_WIDTH_TYPES
_WIDTH_PROMOTE_TYPES = WIDTH_PROMOTE_TYPES
_WIDTH_PROMOTE_THRESHOLD = 6


def block_width(block: GenUIBlock) -> str:
    """Default grid width for a block, from type and how much data it holds."""
    if block.type in _FULL_WIDTH_TYPES:
        return "full"
    if block.type in _WIDTH_PROMOTE_TYPES:
        count = (
            len(block.items or [])
            + len(block.terms or [])
            + len(block.faqs or [])
        )
        if count >= _WIDTH_PROMOTE_THRESHOLD:
            return "full"
    return "half"


def block_has_min_content(block: GenUIBlock) -> bool:
    """True when a block carries enough real data to be worth rendering.

    Kills degenerate blocks (a 1-row table, a single-item list, a progress
    block with no levels) that otherwise render as thin or empty cards.
    """
    t = block.type
    items = block.items or []
    if t in ("key_points", "steps", "chips"):
        return len(items) >= 2
    if t in ("table", "comparison"):
        if len(items) < 2:
            return False
        data_rows = [r for r in items if not _is_matrix_header(r)]
        return len(data_rows) >= 1
    if t == "progress":
        return any("|" in (i or "") for i in items)
    if t == "metrics":
        return len(items) >= 1
    if t == "timeline":
        return len(items) >= 1
    if t == "key_terms":
        return any((term.definition or "").strip() for term in (block.terms or []))
    if t == "faq":
        return len(block.faqs or []) >= 1
    if t == "summary":
        return len((block.body or "").strip()) >= 8
    if t in ("callout", "quote"):
        return len((block.body or "").strip()) >= 12
    return True


_LEVEL_RE = re.compile(
    r"\b(strong|growing|gap|foundational|weak|expert|advanced|proficient|basic|lacking)\b",
    re.I,
)
_HEADERISH_RE = re.compile(
    r"\b(requirement|evidence|status|skill|level|gap|column|vs\.?)\b",
    re.I,
)


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


def _is_level_row(row: str) -> bool:
    if "|" not in row:
        return False
    parts = [p.strip() for p in row.split("|")]
    if len(parts) != 2:
        return False
    return bool(_LEVEL_RE.search(parts[1])) and not _HEADERISH_RE.search(parts[0])


def _is_matrix_header(row: str) -> bool:
    if "|" not in row:
        return False
    return bool(_HEADERISH_RE.search(row))


def _pipe_items_from_structured(
    structured: dict[str, Any],
    *,
    prefer_cols: int | None = None,
    include_levels: bool = False,
) -> list[str]:
    """Collect pipe rows; keep consistent column counts for table UI."""
    items: list[str] = []
    for key in ("matrix_rows", "comparisons"):
        for row in structured.get(key) or []:
            if isinstance(row, str) and "|" in row:
                items.append(row.strip()[:400])
    for sec in structured.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for b in sec.get("bullets") or []:
            if isinstance(b, str) and "|" in b:
                items.append(b.strip()[:400])
    for row in structured.get("key_points") or []:
        if not isinstance(row, str) or "|" not in row:
            continue
        if _is_level_row(row) and not include_levels:
            continue
        items.append(row.strip()[:400])
    if include_levels:
        for row in structured.get("levels") or []:
            if isinstance(row, str) and "|" in row:
                items.append(row.strip()[:400])

    # Drop pure level rows from matrix unless requested
    if not include_levels:
        items = [i for i in items if not _is_level_row(i)]

    # Prefer rows matching dominant (or preferred) column count
    counted: list[tuple[str, int]] = []
    for i in items:
        cols = len([c.strip() for c in i.split("|")])
        if cols >= 2:
            counted.append((i, cols))
    if not counted:
        return []

    if prefer_cols and any(c == prefer_cols for _, c in counted):
        target = prefer_cols
    else:
        # Prefer headers / 3-col matrices for job comparison tables
        freq: dict[int, int] = {}
        for _, c in counted:
            freq[c] = freq.get(c, 0) + 1
        # Bias slightly toward 3 columns when present (requirement matrices)
        target = max(freq.keys(), key=lambda c: (freq[c], c == 3, c))

    uniq: list[str] = []
    seen: set[str] = set()
    # Keep header-like rows first
    ordered = sorted(
        counted,
        key=lambda pair: (0 if _is_matrix_header(pair[0]) else 1, pair[0]),
    )
    for text, cols in ordered:
        if cols != target:
            continue
        if text not in seen:
            seen.add(text)
            uniq.append(text)
    return uniq[:14]


def _prose_key_points(structured: dict[str, Any]) -> list[str]:
    """Key points without qualitative level rows (those belong in progress)."""
    out: list[str] = []
    for item in structured.get("key_points") or []:
        text = str(item).strip()
        if not text or _is_level_row(text):
            continue
        if "|" in text and _is_matrix_header(text):
            continue
        if "|" in text and len(text.split("|")) >= 3:
            continue
        out.append(text[:400])
        if len(out) >= 14:
            break
    return out


def _clean_steps(items: list[str]) -> list[str]:
    """Drop label-only "Title:" markers and de-dupe so steps read as actions."""
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        # e.g. "Analyze Job Descriptions:" is a section marker, not a step
        if text.endswith(":") and len(text.split()) <= 6:
            continue
        key = text.lower().rstrip(".")
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _steps_from_structured(structured: dict[str, Any]) -> list[str]:
    for key in ("ordered_actions", "learning_path", "design_process", "steps", "update_checklist"):
        items = _str_list(structured.get(key))
        cleaned = _clean_steps(items)
        if cleaned:
            return cleaned
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
    return _clean_steps(_str_list(steps, limit=12))


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


def _is_real_faq_answer(answer: str) -> bool:
    """False when an 'answer' is empty or itself just a list of questions."""
    # Strip bold markers first so "**Have I…?**" still counts as a question.
    text = re.sub(r"\*\*", "", answer or "").strip()
    if not text:
        return False
    parts = [
        p.strip().lstrip("-•* ").strip()
        for p in re.split(r"\s+-\s+|(?<=[?.!])\s+", text)
    ]
    parts = [p for p in parts if p]
    if parts and all(p.endswith("?") for p in parts):
        return False
    return True


def _faq_from_structured(structured: dict[str, Any]) -> list[FaqItem]:
    faqs: list[FaqItem] = []
    for item in structured.get("faq") or []:
        if isinstance(item, dict):
            q = str(item.get("question") or "").strip()
            a = str(item.get("answer") or "").strip()
            if q and _is_real_faq_answer(a):
                faqs.append(FaqItem(question=q[:300], answer=a[:800]))
    for item in structured.get("misconceptions") or []:
        if isinstance(item, dict):
            q = str(item.get("question") or item.get("myth") or "").strip()
            a = str(item.get("answer") or item.get("correction") or "").strip()
            if q and _is_real_faq_answer(a):
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
    # No real priority/gap/risk — do not fabricate a callout from the summary.
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


def _diagram_nodes(raw: Any) -> list[DiagramNode]:
    nodes: list[DiagramNode] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return nodes
    for i, x in enumerate(raw):
        if not isinstance(x, dict):
            continue
        nid = str(x.get("id") or x.get("label") or f"node_{i}").strip()
        label = str(x.get("label") or x.get("id") or "").strip()
        if not nid or not label or nid in seen:
            continue
        detail = str(x.get("detail") or "").strip() or None
        nodes.append(
            DiagramNode(id=nid, label=label[:120], detail=detail[:400] if detail else None)
        )
        seen.add(nid)
    return nodes[:12]


def _diagram_edges(raw: Any, valid_ids: set[str]) -> list[DiagramEdge]:
    edges: list[DiagramEdge] = []
    seen: set[tuple[str, str, str]] = set()
    if not isinstance(raw, list):
        return edges
    for x in raw:
        if not isinstance(x, dict):
            continue
        src = str(x.get("source") or "").strip()
        tgt = str(x.get("target") or "").strip()
        if not src or not tgt or src not in valid_ids or tgt not in valid_ids:
            continue
        label = str(x.get("label") or "").strip()[:120] or None
        key = (src, tgt, label or "")
        if key in seen:
            continue
        seen.add(key)
        edges.append(DiagramEdge(source=src, target=tgt, label=label))
    return edges[:20]


def _sequence_actors_and_messages(
    raw_actors: Any, raw_messages: Any
) -> tuple[list[str], list[SequenceMessage]]:
    actors: list[str] = []
    if isinstance(raw_actors, list):
        actors = [str(a).strip()[:60] for a in raw_actors if str(a).strip()]

    messages: list[SequenceMessage] = []
    if isinstance(raw_messages, list):
        for i, x in enumerate(raw_messages[:24]):
            if not isinstance(x, dict):
                continue
            src = str(x.get("source") or "").strip()[:60]
            tgt = str(x.get("target") or "").strip()[:60]
            label = str(x.get("label") or "").strip()
            if not src or not tgt or not label:
                continue
            for actor in (src, tgt):
                if actor not in actors:
                    actors.append(actor)
            try:
                order = int(x.get("order"))
            except (TypeError, ValueError):
                order = i
            note = str(x.get("note") or "").strip() or None
            messages.append(
                SequenceMessage(
                    source=src,
                    target=tgt,
                    label=label[:120],
                    order=order,
                    note=note[:400] if note else None,
                )
            )

    actors = actors[:8]
    actor_set = set(actors)
    messages = [m for m in messages if m.source in actor_set and m.target in actor_set]
    return actors, messages


def _levels_items(structured: dict[str, Any]) -> list[str]:
    items = _str_list(structured.get("levels"))
    if items:
        return [i for i in items if "|" in i][:10] or items[:10]
    out: list[str] = []
    for kp in structured.get("key_points") or []:
        if isinstance(kp, str) and _is_level_row(kp):
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
        # A colon-terminated lead-in ("…consider the following:") is not a summary.
        if body.endswith(":"):
            body = ""
        if not body and structured.get("key_points"):
            body = " ".join(_str_list(structured.get("key_points"), limit=3))
        if body:
            block = GenUIBlock(type="summary", title=title or "Overview", body=body[:2000])

    elif btype == "key_points" or hint == "key_points":
        items = _prose_key_points(structured)
        if not items:
            for sec in structured.get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                heading = str(sec.get("heading") or "")
                if re.search(r"checklist|step|how|process", heading, re.I):
                    continue
                for b in _str_list(sec.get("bullets"), limit=6):
                    if not _is_level_row(b) and "|" not in b:
                        items.append(b)
            items = _str_list(items)
        if items:
            block = GenUIBlock(type="key_points", title=title or "Key points", items=items)

    elif btype == "key_terms" or hint in ("concepts", "terms"):
        terms = _terms_from_structured(structured)
        # Drop empty-definition noise (common when falling back from bullets)
        terms = [t for t in terms if t.definition.strip()]
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
        if items:
            # Keep only consistent multi-col rows
            items = _pipe_items_from_structured(
                {"matrix_rows": items}, prefer_cols=None, include_levels=False
            ) or items
        if not items:
            items = _pipe_items_from_structured(structured, include_levels=False)
        if items:
            block = GenUIBlock(type="table", title=title or "Comparison", items=items)

    elif btype == "comparison" or hint == "comparisons":
        items = _str_list(structured.get("comparisons"))
        if not items:
            items = _pipe_items_from_structured(structured, prefer_cols=3, include_levels=False)
        if not items:
            items = _pipe_items_from_structured(structured, include_levels=False)
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

    elif btype == "flow_diagram" or hint == "process_flow":
        pf = structured.get("process_flow") or {}
        nodes = _diagram_nodes(pf.get("nodes"))
        valid_ids = {n.id for n in nodes}
        edges = _diagram_edges(pf.get("edges"), valid_ids)
        if len(nodes) >= 2 and edges:
            block = GenUIBlock(
                type="flow_diagram", title=title or "How it works", nodes=nodes, edges=edges
            )

    elif btype == "sequence_diagram" or hint == "interaction_sequence":
        seq = structured.get("interaction_sequence") or {}
        actors, messages = _sequence_actors_and_messages(
            seq.get("actors"), seq.get("messages")
        )
        if len(actors) >= 2 and messages:
            block = GenUIBlock(
                type="sequence_diagram", title=title or "Sequence", actors=actors, messages=messages
            )

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
        if not block_has_min_content(assembled):
            dropped.append({"type": btype, "reason": "insufficient content"})
            continue
        explicit = entry.get("width")
        width = explicit if explicit in ("full", "half") else block_width(assembled)
        assembled = assembled.model_copy(update={"width": width})
        blocks.append(assembled)
        if len(blocks) >= 10:
            break

    blocks, deduped = _dedupe_overlapping_blocks(blocks)
    dropped.extend(deduped)
    blocks = _tag_blocks_with_themes(blocks, structured.get("themes") or [])
    return blocks, dropped


def _norm_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower()).rstrip(".")


def _block_text(block: GenUIBlock) -> str:
    parts = [block.title or "", block.body or ""]
    parts.extend(block.items or [])
    parts.extend(f"{t.term} {t.definition}" for t in block.terms or [])
    parts.extend(f"{f.question} {f.answer}" for f in block.faqs or [])
    return " ".join(parts).lower()


def _tag_blocks_with_themes(
    blocks: list[GenUIBlock],
    themes: list[Any],
) -> list[GenUIBlock]:
    """
    Attach matching themes as block tags so chip filtering works on real
    metadata instead of the frontend's substring fallback.
    """
    labels = [str(t).strip() for t in themes if str(t).strip()]
    if not labels:
        return blocks

    def matches(theme: str, hay: str) -> bool:
        words = [w for w in re.findall(r"[a-z0-9]+", theme.lower()) if len(w) >= 4]
        if not words:
            words = re.findall(r"[a-z0-9]+", theme.lower())
        return any(w in hay for w in words)

    out: list[GenUIBlock] = []
    for block in blocks:
        if block.type == "chips" or block.tags:
            out.append(block)
            continue
        hay = _block_text(block)
        matched = [t for t in labels if matches(t, hay)][:6]
        out.append(
            block.model_copy(update={"tags": matched}) if matched else block
        )
    return out


def _dedupe_overlapping_blocks(
    blocks: list[GenUIBlock],
) -> tuple[list[GenUIBlock], list[dict[str, str]]]:
    """When steps already cover the key points, don't repeat them as a list."""
    step_lines = [
        _norm_line(i)
        for b in blocks
        if b.type == "steps"
        for i in (b.items or [])
    ]
    if not step_lines:
        return blocks, []

    def covered_by_steps(item: str) -> bool:
        line = _norm_line(item)
        if line in step_lines:
            return True
        # "Label — detail" steps embed the source bullet; treat containment
        # of a substantial bullet as a duplicate too.
        return len(line) >= 20 and any(line in s for s in step_lines)

    out: list[GenUIBlock] = []
    dropped: list[dict[str, str]] = []
    for block in blocks:
        if block.type == "key_points" and block.items:
            unique = [i for i in block.items if not covered_by_steps(i)]
            if len(unique) < 2:
                dropped.append({"type": "key_points", "reason": "duplicates steps"})
                continue
            block = block.model_copy(update={"items": unique})
        out.append(block)
    return out, dropped


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

    from app.visual_summary.planning.layout_stabilize import sanitize_presentation_profile

    summary = str(structured.get("summary") or "").strip()
    plain = summary or (blocks[0].body if blocks[0].body else goal[:200])
    profile = sanitize_presentation_profile(
        str(layout_plan.get("presentation_profile") or ""),
        goal=goal,
        fallback="workspace_derived",
    )
    title = workspace_name.strip() or profile.replace("_", " ").title() or "Visual summary"
    if goal and len(goal) < 80:
        title = goal[:80]

    return {
        "type": "generative_ui",
        "title": title[:120],
        "plain_summary": plain[:600],
        "presentation_profile": profile,
        "blocks": [b.model_dump() for b in blocks],
        "source_files": list(source_files or []),
        "assembly_meta": {
            "assembled_blocks": [b.type for b in blocks],
            "dropped_blocks": dropped,
            "render_fallback_used": False,
        },
    }
