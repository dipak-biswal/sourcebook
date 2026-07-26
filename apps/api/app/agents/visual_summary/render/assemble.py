"""Code-first GenUI block assembly from layout outline + structured content."""

from __future__ import annotations

import re
from typing import Any

from app.agents.visual_summary.blocks.gen_ui import (
    ComparePath,
    DiagramEdge,
    DiagramNode,
    FaqItem,
    GenUIBlock,
    KeyTerm,
    SequenceMessage,
    _normalize_block_dict,
)
from app.agents.visual_summary.blocks.registry import FULL_WIDTH_TYPES, WIDTH_PROMOTE_TYPES


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
    if t == "flow_diagram":
        return len(block.nodes or []) >= 2 and len(block.edges or []) >= 1
    if t == "sequence_diagram":
        return len(block.actors or []) >= 2 and len(block.messages or []) >= 1
    if t == "compare_paths":
        paths = block.paths or []
        ok = 0
        for p in paths:
            if len(p.nodes or []) >= 2 and len(p.edges or []) >= 1:
                ok += 1
        return ok >= 2
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
        style = str(x.get("style") or "").strip().lower() or None
        if style not in ("fail", "ok", "dashed", None):
            style = None
        edges.append(DiagramEdge(source=src, target=tgt, label=label, style=style))
    return edges[:20]


def _chain_from_labels(labels: list[str], *, prefix: str) -> tuple[list[DiagramNode], list[DiagramEdge]]:
    nodes: list[DiagramNode] = []
    edges: list[DiagramEdge] = []
    for i, lab in enumerate(labels[:6]):
        nid = f"{prefix}{i}"
        nodes.append(DiagramNode(id=nid, label=lab[:100]))
        if i > 0:
            edges.append(
                DiagramEdge(source=f"{prefix}{i - 1}", target=nid, label=None)
            )
    return nodes, edges


def _split_arrow_chain(text: str) -> list[str]:
    if not re.search(r"→|->|⇒", text or ""):
        return []
    parts = re.split(r"\s*(?:→|->|⇒)\s*", text)
    return [p.strip(" .;:") for p in parts if p.strip()]


def _compare_paths_from_section(
    sec: dict[str, Any],
    local: dict[str, Any],
) -> list[ComparePath] | None:
    """Build dual paths (Without / With) from section prose, bullets, or tables."""
    heading = str(sec.get("heading") or "")
    body = str(sec.get("body") or "")
    bullets = _str_list(sec.get("bullets"), limit=16)

    without_labels: list[str] = []
    with_labels: list[str] = []
    without_result = ""
    with_result = ""

    # 1) Explicit arrow chains tagged Without / With
    for text in [body, *bullets]:
        low = text.lower()
        chain = _split_arrow_chain(text)
        if len(chain) < 2:
            continue
        if re.search(r"\bwithout\b", low):
            without_labels = chain
        elif re.search(r"\bwith\b", low) and "without" not in low:
            with_labels = chain

    # 2) Pipe rows: Without col | With col (after optional header)
    pipe_rows = [b for b in bullets if b.count("|") >= 1]
    for line in body.splitlines():
        if line.count("|") >= 1 and not re.match(r"^[\s|:-]+$", line.strip()):
            pipe_rows.append(line.strip())
    data_rows: list[tuple[str, str]] = []
    for row in pipe_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if len(cells) < 2:
            continue
        left, right = cells[0], cells[1]
        if re.search(r"\b(without|with|risk|result)\b", f"{left} {right}", re.I) and not re.search(
            r"→|->|⇒|[a-z].*[a-z]", left, re.I
        ):
            # header-ish
            continue
        if re.fullmatch(r"[\s\-:]+", left) or re.fullmatch(r"[\s\-:]+", right):
            continue
        data_rows.append((left, right))

    if data_rows and (not without_labels or not with_labels):
        # First content row becomes chain steps if multi-clause; else single-step summary nodes
        lefts = [r[0] for r in data_rows[:4]]
        rights = [r[1] for r in data_rows[:4]]
        if not without_labels:
            without_labels = lefts if len(lefts) >= 2 else [
                "Update DB",
                "Publish message",
                "Broker",
            ]
            if len(lefts) == 1:
                without_result = lefts[0]
                without_labels = ["Update DB", "Publish message", "Broker"]
        if not with_labels:
            with_labels = rights if len(rights) >= 2 else [
                "Update DB + outbox",
                "Outbox processor",
                "Broker",
            ]
            if len(rights) == 1:
                with_result = rights[0]
                with_labels = ["Update DB + outbox", "Outbox processor", "Broker"]
        if len(data_rows) >= 2:
            without_result = without_result or data_rows[-1][0]
            with_result = with_result or data_rows[-1][1]

    # 3) Defaults when heading is Without vs With but no structure
    if (not without_labels or not with_labels) and re.search(
        r"\b(without|vs\.?|versus)\b", heading, re.I
    ):
        without_labels = without_labels or ["Update DB", "Publish message", "Broker"]
        with_labels = with_labels or [
            "Update DB + outbox",
            "Outbox processor",
            "Broker",
        ]
        if not without_result:
            without_result = "DB updated, message may be lost"
        if not with_result:
            with_result = "Message delivered eventually"

    if len(without_labels) < 2 or len(with_labels) < 2:
        return None

    w_nodes, w_edges = _chain_from_labels(without_labels, prefix="wo_")
    # Fail the last edge on the without path when risk language is present.
    blob = f"{heading}\n{body}\n" + "\n".join(bullets)
    if w_edges and re.search(r"\b(lost|fail|risk|inconsist|drop|missing)\b", blob, re.I):
        last = w_edges[-1]
        w_edges[-1] = DiagramEdge(
            source=last.source,
            target=last.target,
            label=last.label or "Failure!",
            style="fail",
        )
        if not without_result:
            without_result = "Message lost / inconsistent state"

    y_nodes, y_edges = _chain_from_labels(with_labels, prefix="wi_")
    if not with_result and re.search(r"\breliable|eventual|delivered|atomic\b", blob, re.I):
        with_result = "Message delivered reliably"

    return [
        ComparePath(
            id="without",
            label="Without",
            nodes=w_nodes,
            edges=w_edges,
            result=without_result[:240] or None,
        ),
        ComparePath(
            id="with",
            label="With",
            nodes=y_nodes,
            edges=y_edges,
            result=with_result[:240] or None,
        ),
    ]


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


def _section_by_index(
    structured: dict[str, Any], section_index: Any
) -> dict[str, Any] | None:
    """1-based section_index from study-sheet outline → section dict."""
    try:
        idx = int(section_index)
    except (TypeError, ValueError):
        return None
    if idx < 1:
        return None
    sections = [
        s for s in (structured.get("sections") or []) if isinstance(s, dict)
    ]
    if idx > len(sections):
        return None
    return sections[idx - 1]


def _structured_from_section(
    sec: dict[str, Any],
    global_structured: dict[str, Any],
) -> dict[str, Any]:
    """Build a local structured blob so assemble can fill one panel from one section."""
    bullets = _str_list(sec.get("bullets"), limit=16)
    body = str(sec.get("body") or "").strip()
    pipe_from_bullets = [b for b in bullets if "|" in b]
    prose_bullets = [b for b in bullets if "|" not in b]
    pipe_from_body: list[str] = []
    steps_from_body: list[str] = []
    for line in body.splitlines():
        ln = line.strip()
        if not ln:
            continue
        if ln.count("|") >= 1 and not re.match(r"^[\s|:-]+$", ln):
            pipe_from_body.append(ln[:400])
            continue
        m = re.match(r"^(?:\d+[.)]|[-•*])\s+(.+)$", ln)
        if m:
            steps_from_body.append(m.group(1).strip()[:400])

    matrix = pipe_from_bullets or pipe_from_body
    steps = steps_from_body or (
        prose_bullets
        if re.search(
            r"\b(step|transaction|how|process|checklist|procedure)\b",
            str(sec.get("heading") or ""),
            re.I,
        )
        else []
    )

    # Simple chain flow from ordered steps / arrow phrases.
    flow_nodes: list[dict[str, Any]] = []
    flow_edges: list[dict[str, Any]] = []
    chain_src = steps_from_body or prose_bullets
    arrow_parts: list[str] = []
    for text in [body, *bullets]:
        if re.search(r"→|->|⇒", text):
            parts = re.split(r"\s*(?:→|->|⇒)\s*", text)
            parts = [p.strip(" .;:") for p in parts if p.strip()]
            if len(parts) >= 2:
                arrow_parts = parts
                break
    labels = arrow_parts if len(arrow_parts) >= 2 else chain_src[:8]
    if len(labels) >= 2:
        for i, lab in enumerate(labels):
            nid = f"s{i}"
            flow_nodes.append({"id": nid, "label": lab[:100]})
            if i > 0:
                flow_edges.append(
                    {"source": f"s{i - 1}", "target": nid, "label": None}
                )

    actors: list[str] = []
    messages: list[dict[str, Any]] = []
    if len(labels) >= 2 and re.search(
        r"\b(sequence|service|broker|consumer|producer)\b",
        str(sec.get("heading") or body),
        re.I,
    ):
        actors = [lab[:60] for lab in labels[:6]]
        for i in range(len(actors) - 1):
            messages.append(
                {
                    "source": actors[i],
                    "target": actors[i + 1],
                    "label": "next",
                    "order": i,
                }
            )

    return {
        "summary": body[:2000] if body else " ".join(prose_bullets[:3]),
        "key_points": prose_bullets or steps_from_body,
        "matrix_rows": matrix,
        "comparisons": matrix,
        "ordered_actions": steps or prose_bullets,
        "process_flow": {"nodes": flow_nodes, "edges": flow_edges},
        "interaction_sequence": {"actors": actors, "messages": messages},
        "priority_message": {
            "title": str(sec.get("heading") or "Note")[:80],
            "body": (body or " ".join(prose_bullets[:2]))[:600],
        },
        "themes": global_structured.get("themes") or [],
        "sections": [sec],
    }


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

    # Study-sheet panels: prefer data from the matching answer section.
    local = structured
    sec = _section_by_index(structured, outline_entry.get("section_index"))
    if sec is not None:
        local = _structured_from_section(sec, structured)

    block: GenUIBlock | None = None

    if btype == "summary" or hint == "summary":
        body = str(local.get("summary") or "").strip()
        # A colon-terminated lead-in ("…consider the following:") is not a summary.
        if body.endswith(":"):
            body = ""
        if not body and local.get("key_points"):
            body = " ".join(_str_list(local.get("key_points"), limit=3))
        if not body and sec is None:
            body = str(structured.get("summary") or "").strip()
            if body.endswith(":"):
                body = ""
        if body:
            block = GenUIBlock(type="summary", title=title or "Overview", body=body[:2000])

    elif btype == "key_points" or hint == "key_points":
        items = _prose_key_points(local)
        if not items and sec is not None:
            items = _str_list(local.get("key_points") or local.get("ordered_actions"))
        if not items:
            for s in structured.get("sections") or []:
                if not isinstance(s, dict):
                    continue
                heading = str(s.get("heading") or "")
                if re.search(r"checklist|step|how|process", heading, re.I):
                    continue
                for b in _str_list(s.get("bullets"), limit=6):
                    if not _is_level_row(b) and "|" not in b:
                        items.append(b)
            items = _str_list(items)
        # Study panels: surface section intro as body above bullets.
        intro = ""
        if sec is not None:
            intro = str(local.get("summary") or "").strip()
            if intro and items:
                # Avoid duplicating the same text as first bullet.
                if items and intro.rstrip(".") == items[0].rstrip("."):
                    intro = ""
        if items:
            block = GenUIBlock(
                type="key_points",
                title=title or "Key points",
                items=items,
                body=intro[:800] or None,
            )
        elif intro:
            block = GenUIBlock(
                type="summary",
                title=title or "Overview",
                body=intro[:2000],
            )

    elif btype == "key_terms" or hint in ("concepts", "terms"):
        terms = _terms_from_structured(local if sec is not None else structured)
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
        items = _steps_from_structured(local)
        if not items and sec is None:
            items = _steps_from_structured(structured)
        if not items and sec is not None:
            items = _str_list(local.get("key_points") or local.get("ordered_actions"))
        if items:
            block = GenUIBlock(type="steps", title=title or "Steps", items=items)

    elif btype == "table" or hint == "matrix_rows":
        items = _str_list(local.get("matrix_rows"))
        if items:
            # Keep only consistent multi-col rows
            items = _pipe_items_from_structured(
                {"matrix_rows": items}, prefer_cols=None, include_levels=False
            ) or items
        if not items and sec is None:
            items = _pipe_items_from_structured(structured, include_levels=False)
        if items:
            block = GenUIBlock(type="table", title=title or "Comparison", items=items)
        elif sec is not None:
            # Study sheet: fall back to bullets so the panel is not dropped.
            fb = _str_list(local.get("key_points") or local.get("ordered_actions"))
            if fb:
                block = GenUIBlock(type="key_points", title=title or "Details", items=fb)

    elif btype == "compare_paths" or hint == "compare_paths":
        paths: list[ComparePath] | None = None
        raw_paths = local.get("compare_paths") or structured.get("compare_paths")
        if isinstance(raw_paths, dict) and isinstance(raw_paths.get("paths"), list):
            raw_paths = raw_paths["paths"]
        if isinstance(raw_paths, list):
            paths = []
            for i, p in enumerate(raw_paths[:4]):
                if not isinstance(p, dict):
                    continue
                nodes = _diagram_nodes(p.get("nodes"))
                valid = {n.id for n in nodes}
                edges = _diagram_edges(p.get("edges"), valid)
                if len(nodes) < 2 or not edges:
                    continue
                paths.append(
                    ComparePath(
                        id=str(p.get("id") or f"path_{i}"),
                        label=str(p.get("label") or f"Path {i + 1}")[:80],
                        nodes=nodes,
                        edges=edges,
                        result=(str(p.get("result") or "").strip()[:240] or None),
                    )
                )
            if len(paths) < 2:
                paths = None
        if paths is None and sec is not None:
            paths = _compare_paths_from_section(sec, local)
        prose_items = _str_list(
            local.get("key_points") or local.get("comparisons") or local.get("matrix_rows"),
            limit=8,
        )
        if paths and len(paths) >= 2:
            block = GenUIBlock(
                type="compare_paths",
                title=title or "Without vs With",
                paths=paths,
                items=prose_items or None,
            )
        elif sec is not None:
            # Fall back to comparison table / key points
            items = prose_items or _str_list(local.get("comparisons") or local.get("matrix_rows"))
            if items:
                block = GenUIBlock(
                    type="comparison" if any("|" in i for i in items) else "key_points",
                    title=title or "Comparison",
                    items=items,
                )

    elif btype == "comparison" or hint == "comparisons":
        # Prefer dual-path diagram for Without vs With study sections.
        if sec is not None and re.search(
            r"\b(without|vs\.?|versus|with\s+vs)\b",
            str(sec.get("heading") or ""),
            re.I,
        ):
            paths = _compare_paths_from_section(sec, local)
            if paths and len(paths) >= 2:
                prose_items = _str_list(
                    local.get("key_points")
                    or local.get("comparisons")
                    or local.get("matrix_rows"),
                    limit=8,
                )
                block = GenUIBlock(
                    type="compare_paths",
                    title=title or "Without vs With",
                    paths=paths,
                    items=prose_items or None,
                )
        if block is None:
            items = _str_list(local.get("comparisons") or local.get("matrix_rows"))
            if not items and sec is None:
                items = _pipe_items_from_structured(structured, prefer_cols=3, include_levels=False)
            if not items and sec is None:
                items = _pipe_items_from_structured(structured, include_levels=False)
            if items:
                block = GenUIBlock(type="comparison", title=title or "Tradeoffs", items=items)
            elif sec is not None:
                fb = _str_list(local.get("key_points") or local.get("ordered_actions"))
                if fb:
                    block = GenUIBlock(type="key_points", title=title or "Comparison", items=fb)

    elif btype == "progress" or hint == "levels":
        items = _levels_items(local if sec is not None else structured)
        if items:
            block = GenUIBlock(type="progress", title=title or "Levels", items=items)

    elif btype == "faq" or hint in ("faq", "misconceptions"):
        faqs = _faq_from_structured(structured)
        if faqs:
            block = GenUIBlock(type="faq", title=title or "FAQ", faqs=faqs)

    elif btype == "callout" or hint == "priority_message":
        ctitle, body = _callout_body(local if sec is not None else structured)
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
        items = _str_list(
            (local if sec is not None else structured).get("milestones")
            or (local if sec is not None else structured).get("timeline")
        )
        if not items:
            items = [
                i
                for i in _pipe_items_from_structured(
                    local if sec is not None else structured
                )
                if re.search(r"\b(19|20)\d{2}\b", i)
            ]
        if items:
            block = GenUIBlock(type="timeline", title=title or "Timeline", items=items)

    elif btype == "metrics" or hint == "metrics":
        items = _str_list((local if sec is not None else structured).get("metrics"))
        if items:
            block = GenUIBlock(type="metrics", title=title or "Metrics", items=items)

    elif btype == "flow_diagram" or hint == "process_flow":
        pf = local.get("process_flow") or {}
        if not (pf.get("nodes") and pf.get("edges")) and sec is None:
            pf = structured.get("process_flow") or {}
        nodes = _diagram_nodes(pf.get("nodes"))
        valid_ids = {n.id for n in nodes}
        edges = _diagram_edges(pf.get("edges"), valid_ids)
        # Prose companion so study panels keep bullets alongside the figure.
        prose_items = _str_list(
            local.get("key_points") or local.get("ordered_actions"), limit=8
        )
        prose_body = str(local.get("summary") or "").strip()[:600] or None
        if len(nodes) >= 2 and edges:
            block = GenUIBlock(
                type="flow_diagram",
                title=title or "How it works",
                nodes=nodes,
                edges=edges,
                items=prose_items or None,
                body=prose_body if not prose_items else None,
            )
        elif sec is not None:
            fb = prose_items or _str_list(
                local.get("ordered_actions") or local.get("key_points")
            )
            if fb:
                block = GenUIBlock(type="steps", title=title or "Flow", items=fb)

    elif btype == "sequence_diagram" or hint == "interaction_sequence":
        seq = local.get("interaction_sequence") or {}
        if not (seq.get("actors") and seq.get("messages")) and sec is None:
            seq = structured.get("interaction_sequence") or {}
        actors, messages = _sequence_actors_and_messages(
            seq.get("actors"), seq.get("messages")
        )
        prose_items = _str_list(
            local.get("key_points") or local.get("ordered_actions"), limit=8
        )
        prose_body = str(local.get("summary") or "").strip()[:600] or None
        if len(actors) >= 2 and messages:
            block = GenUIBlock(
                type="sequence_diagram",
                title=title or "Sequence",
                actors=actors,
                messages=messages,
                items=prose_items or None,
                body=prose_body if not prose_items else None,
            )
        elif sec is not None:
            pf = local.get("process_flow") or {}
            nodes = _diagram_nodes(pf.get("nodes"))
            valid_ids = {n.id for n in nodes}
            edges = _diagram_edges(pf.get("edges"), valid_ids)
            if len(nodes) >= 2 and edges:
                block = GenUIBlock(
                    type="flow_diagram",
                    title=title or "End-to-end",
                    nodes=nodes,
                    edges=edges,
                    items=prose_items or None,
                    body=prose_body if not prose_items else None,
                )
            else:
                fb = prose_items or _str_list(
                    local.get("ordered_actions") or local.get("key_points")
                )
                if fb:
                    block = GenUIBlock(type="steps", title=title or "End-to-end", items=fb)

    if block is None:
        return None
    tags_out = list(tag_list or [])
    # Prefer panel_index for display chrome; fall back to section_index.
    panel_n = outline_entry.get("panel_index")
    if panel_n is None:
        panel_n = outline_entry.get("section_index")
    if panel_n is not None:
        try:
            tag = f"__section:{int(panel_n)}"
            if tag not in tags_out:
                tags_out = [tag, *tags_out]
        except (TypeError, ValueError):
            pass
    if tags_out:
        block = block.model_copy(update={"tags": tags_out[:6]})
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
    *,
    max_blocks: int = 10,
) -> tuple[list[GenUIBlock], list[dict[str, str]]]:
    """
    Assemble GenUI blocks from plan outline.

    Returns (blocks, dropped) where dropped has type + reason.
    """
    blocks: list[GenUIBlock] = []
    dropped: list[dict[str, str]] = []
    if not outline:
        return blocks, dropped

    # Study sheets need more panels; also when outline itself is longer.
    cap = max_blocks
    if any(
        isinstance(e, dict) and e.get("section_index") is not None for e in outline
    ):
        cap = max(cap, 12)
    if len(outline) > cap:
        cap = min(12, len(outline))

    for entry in outline:
        if not isinstance(entry, dict):
            continue
        btype = str(entry.get("type") or "block")
        assembled = assemble_block(entry, structured)
        if assembled is None:
            # Last-chance study-sheet panel: never leave a hole if section has text.
            sec = _section_by_index(structured, entry.get("section_index"))
            if sec is not None:
                local = _structured_from_section(sec, structured)
                fb = _str_list(
                    local.get("key_points")
                    or local.get("ordered_actions")
                    or ([local.get("summary")] if local.get("summary") else [])
                )
                if fb:
                    title = str(entry.get("title") or sec.get("heading") or "Section")
                    if len(fb) == 1 and len(fb[0]) > 80:
                        assembled = GenUIBlock(
                            type="summary", title=title[:120], body=fb[0][:2000]
                        )
                    else:
                        assembled = GenUIBlock(
                            type="key_points", title=title[:120], items=fb
                        )
            if assembled is None:
                dropped.append(
                    {
                        "type": btype,
                        "reason": f"no data for source_hint={entry.get('source_hint') or btype}",
                    }
                )
                continue
        if not block_has_min_content(assembled):
            # Study-sheet: keep thin summary panels rather than dropping order.
            if entry.get("section_index") is not None and (
                (assembled.body and len(assembled.body.strip()) >= 8)
                or (assembled.items and len(assembled.items) >= 1)
            ):
                pass
            else:
                dropped.append({"type": btype, "reason": "insufficient content"})
                continue
        explicit = entry.get("width")
        width = explicit if explicit in ("full", "half") else block_width(assembled)
        # Study-sheet outline may set half for denser boards; honor it.
        if entry.get("section_index") is not None and explicit not in ("full", "half"):
            width = "full"
        assembled = assembled.model_copy(update={"width": width})
        # Ensure panel chrome tag survives model_copy(width=…).
        panel_n = entry.get("panel_index", entry.get("section_index"))
        if panel_n is not None:
            tags = list(assembled.tags or [])
            tag = f"__section:{int(panel_n)}"
            if tag not in tags:
                tags = [tag, *tags][:6]
            assembled = assembled.model_copy(update={"tags": tags})
        blocks.append(assembled)
        if len(blocks) >= cap:
            break

    # Dedupe is harmful for study sheets (many sections share vocabulary).
    if not any(
        isinstance(e, dict) and e.get("section_index") is not None for e in outline
    ):
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

    from app.agents.visual_summary.planning.layout_stabilize import sanitize_presentation_profile

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
