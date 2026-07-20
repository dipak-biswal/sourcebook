"""Generative UI schema and block normalization for visual summaries."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.blocks import BLOCK_TYPE_SET


BlockType = Literal[
    "summary",
    "key_points",
    "key_terms",
    "faq",
    "callout",
    "steps",
    "chips",
    "table",
    "metrics",
    "timeline",
    "quote",
    "comparison",
    "progress",
    "chart",
    "flow_diagram",
    "sequence_diagram",
]


class KeyTerm(BaseModel):
    term: str
    definition: str


class MeasureItem(BaseModel):
    """Structured form of a metrics/progress/chart row ("Label | 42 ms")."""

    label: str
    value: str
    unit: str | None = None
    numeric: float | None = None


_NUMERIC_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_measure_item(text: str) -> MeasureItem | None:
    """
    Parse a pipe row into a structured measure.

    "Latency | 200 ms" → label=Latency value="200 ms" numeric=200 unit="ms"
    "Coverage | 85%"   → numeric=85 unit="%"
    "Onboarding | Gap" → numeric=None (qualitative value)
    """
    if not text or "|" not in text:
        return None
    label, _, value = text.partition("|")
    label = label.strip()
    value = value.strip()
    if not label or not value:
        return None
    numeric: float | None = None
    unit: str | None = None
    m = _NUMERIC_RE.search(value)
    if m:
        try:
            numeric = float(m.group(0).replace(",", ""))
        except ValueError:
            numeric = None
        if numeric is not None:
            rest = (value[: m.start()] + value[m.end() :]).strip(" ,")
            if rest and len(rest) <= 12:
                unit = rest
    return MeasureItem(label=label, value=value, unit=unit, numeric=numeric)


class FaqItem(BaseModel):
    question: str
    answer: str


class DiagramNode(BaseModel):
    id: str
    label: str
    detail: str | None = None  # example/explanatory text, shown on expand


class DiagramEdge(BaseModel):
    source: str  # DiagramNode.id
    target: str  # DiagramNode.id
    label: str | None = None


class SequenceMessage(BaseModel):
    source: str  # actor name
    target: str  # actor name
    label: str
    order: int
    note: str | None = None  # example/explanatory text, shown on expand


class GenUIBlock(BaseModel):
    type: BlockType
    title: str | None = None
    body: str | None = None
    items: list[str] | None = None
    terms: list[KeyTerm] | None = None
    faqs: list[FaqItem] | None = None
    # Lowercase slugs — matched by interactive chip filters in the web UI
    tags: list[str] | None = None
    # Grid layout hint honored by the web UI (full span vs half column)
    width: Literal["full", "half"] | None = None
    # Structured rows for metrics/progress/chart — derived from items by the
    # engine (never model-supplied) so charts can render real values.
    measures: list[MeasureItem] | None = None
    # flow_diagram: boxes/arrows describing a process or mechanism.
    nodes: list[DiagramNode] | None = None
    edges: list[DiagramEdge] | None = None
    # sequence_diagram: lifelines + ordered messages between named actors.
    actors: list[str] | None = None
    messages: list[SequenceMessage] | None = None
    # 1-based indices into payload.sources (same numbers as [1], [2] in context)
    source_indices: list[int] = Field(default_factory=list)

    @field_validator("source_indices", mode="before")
    @classmethod
    def _coerce_indices(cls, v: Any) -> list[int]:
        if not v:
            return []
        out: list[int] = []
        for x in v:
            try:
                i = int(x)
                if i >= 1:
                    out.append(i)
            except (TypeError, ValueError):
                continue
        # unique, preserve order
        seen: set[int] = set()
        uniq: list[int] = []
        for i in out:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq[:8]


class SourceSnippet(BaseModel):
    index: int
    chunk_id: str
    document_id: str
    filename: str | None = None
    score: float | None = None
    snippet: str


class GenerativeUIPayload(BaseModel):
    """Rendered by the web app as cards (not raw markdown)."""

    type: Literal["generative_ui"] = "generative_ui"
    title: str
    plain_summary: str = Field(
        description="One short paragraph for copy/export and accessibility"
    )
    blocks: list[GenUIBlock] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    sources: list[SourceSnippet] = Field(default_factory=list)
    document_id: str | None = None
    document_filename: str | None = None


def _table_row_to_pipe(row: Any) -> str | None:
    """Coerce a table row object into pipe-separated cells."""
    if isinstance(row, str):
        s = row.strip()
        return s or None
    if isinstance(row, list):
        cells = [str(c).strip() for c in row if str(c).strip()]
        return " | ".join(cells) if cells else None
    if isinstance(row, dict):
        if isinstance(row.get("cells"), list):
            cells = [str(c).strip() for c in row["cells"] if str(c).strip()]
            return " | ".join(cells) if cells else None
        skip = frozenset({"source_indices", "tags", "type", "id"})
        cells = [
            str(v).strip()
            for k, v in row.items()
            if k not in skip and v is not None and str(v).strip()
        ]
        return " | ".join(cells) if cells else None
    return None


def _is_separator_text(text: str) -> bool:
    """Markdown table divider rows and dash-only placeholders."""
    s = text.strip()
    if not s:
        return False
    if re.fullmatch(r"[\s\-:|]+", s):
        return True
    if "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
        if parts and all(re.fullmatch(r"[\s\-:]+", p) for p in parts):
            return True
    return False


def _markdown_table_to_items(body: str) -> list[str]:
    rows: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        if _is_separator_text(line):
            continue
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if parts:
            rows.append(" | ".join(parts))
    return rows


def _clean_cell_text(text: str) -> str:
    """Strip markdown/list noise from render-engine strings shown as plain UI text."""
    s = text.strip()
    s = re.sub(r"^\d+[.)]\s+", "", s)
    s = re.sub(r"^[-•*]\s+", "", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*", "", s)
    return s.strip()


def _clean_display_text(text: str) -> str:
    if "\n" in text:
        return "\n".join(_clean_display_text(line) for line in text.splitlines())
    if "|" in text:
        return " | ".join(_clean_cell_text(part) for part in text.split("|"))
    return _clean_cell_text(text)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = _clean_display_text(value.strip())
        return [s] if s else []
    if isinstance(value, list):
        out: list[str] = []
        for x in value:
            if isinstance(x, str) and x.strip():
                out.append(_clean_display_text(x.strip()))
            elif isinstance(x, dict):
                # {"label": ..., "value": ...} measure rows keep both halves —
                # taking only the value loses the label on metrics tiles.
                label = x.get("label") or x.get("name") or x.get("metric") or x.get("skill")
                value = x.get("value", x.get("score", x.get("level")))
                if label is not None and value is not None and str(label).strip():
                    unit = str(x.get("unit") or "").strip()
                    val = f"{str(value).strip()} {unit}".strip()
                    out.append(
                        _clean_display_text(f"{str(label).strip()} | {val}")
                    )
                    continue
                # {"text": "..."} or {"point": "..."}
                for k in ("text", "point", "item", "value", "content"):
                    if k in x and str(x[k]).strip():
                        out.append(_clean_display_text(str(x[k]).strip()))
                        break
            else:
                t = _clean_display_text(str(x).strip())
                if t:
                    out.append(t)
        return out
    return []


def _normalize_block_dict(raw: Any) -> dict[str, Any] | None:
    """
    Coerce common LLM shape variants so cards are not empty titles only.
    Models often use content/points/bullets/glossary/questions instead of our schema.
    """
    if not isinstance(raw, dict):
        return None
    b = dict(raw)

    # type aliases
    t = str(b.get("type") or b.get("kind") or b.get("block_type") or "summary").lower()
    type_map = {
        "overview": "summary",
        "intro": "summary",
        "introduction": "summary",
        "bullets": "key_points",
        "bullet_points": "key_points",
        "points": "key_points",
        "highlights": "key_points",
        "takeaways": "key_points",
        "glossary": "key_terms",
        "definitions": "key_terms",
        "vocabulary": "key_terms",
        "terms": "key_terms",
        "questions": "faq",
        "q_and_a": "faq",
        "qna": "faq",
        "howto": "steps",
        "how_to": "steps",
        "procedure": "steps",
        "process": "steps",
        "warning": "callout",
        "note": "callout",
        "tip": "callout",
        "important": "callout",
        "stats": "metrics",
        "stat": "metrics",
        "kpis": "metrics",
        "kpi": "metrics",
        "history": "timeline",
        "career": "timeline",
        "milestones": "timeline",
        "pull_quote": "quote",
        "highlight": "quote",
        "compare": "comparison",
        "versus": "comparison",
        "vs": "comparison",
        "matrix": "table",
        "skill_bar": "progress",
        "skills": "progress",
        "bars": "chart",
        "bar_chart": "chart",
        "graph": "chart",
        "flowchart": "flow_diagram",
        "flow": "flow_diagram",
        "process_diagram": "flow_diagram",
        "mechanism": "flow_diagram",
        "sequence": "sequence_diagram",
        "uml_sequence": "sequence_diagram",
        "interaction_diagram": "sequence_diagram",
    }
    b["type"] = type_map.get(t, t if t in BLOCK_TYPE_SET else "summary")

    # title
    if not b.get("title"):
        for k in ("heading", "name", "label"):
            if b.get(k):
                b["title"] = str(b[k])
                break

    # body text aliases
    body = b.get("body") or b.get("content") or b.get("text") or b.get("description") or b.get("summary")
    if body is not None and not isinstance(body, str):
        body = str(body)
    if body:
        b["body"] = _clean_display_text(body.strip())

    # list aliases (models often use "data" instead of "items")
    items = (
        b.get("items")
        or b.get("points")
        or b.get("bullets")
        or b.get("key_points")
        or b.get("steps")
        or b.get("list")
    )
    if items is None and isinstance(b.get("data"), list):
        items = b.get("data")
    items_list = _as_str_list(items)
    if items_list:
        b["items"] = items_list

    # terms / glossary
    terms_raw = b.get("terms") or b.get("glossary") or b.get("definitions") or b.get("vocabulary")
    terms_out: list[dict[str, str]] = []
    if isinstance(terms_raw, list):
        for x in terms_raw:
            if not isinstance(x, dict):
                continue
            term = x.get("term") or x.get("name") or x.get("word") or x.get("key")
            definition = (
                x.get("definition")
                or x.get("meaning")
                or x.get("desc")
                or x.get("description")
                or x.get("value")
            )
            if term and definition:
                terms_out.append(
                    {"term": str(term).strip(), "definition": str(definition).strip()}
                )
    if terms_out:
        b["terms"] = terms_out

    # faq aliases
    faqs_raw = b.get("faqs") or b.get("faq") or b.get("questions") or b.get("qas")
    faqs_out: list[dict[str, str]] = []
    if isinstance(faqs_raw, list):
        for x in faqs_raw:
            if not isinstance(x, dict):
                continue
            q = x.get("question") or x.get("q") or x.get("prompt")
            a = x.get("answer") or x.get("a") or x.get("response")
            if q and a:
                faqs_out.append(
                    {
                        "question": _clean_display_text(str(q).strip()),
                        "answer": _clean_display_text(str(a).strip()),
                    }
                )
    if faqs_out:
        b["faqs"] = faqs_out

    tags_raw = b.get("tags") or b.get("filter_tags") or b.get("themes")
    if tags_raw:
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]
        if isinstance(tags_raw, list):
            b["tags"] = [
                re.sub(r"\s+", "-", str(t).strip().lower())
                for t in tags_raw
                if str(t).strip()
            ]

    if b["type"] == "table":
        headers = b.get("headers") or b.get("columns")
        raw_rows = b.get("rows") or b.get("table")
        data_val = b.get("data")
        if isinstance(data_val, list):
            raw_rows = data_val
        elif isinstance(data_val, str) and data_val.strip() and not raw_rows:
            md_items = _markdown_table_to_items(data_val)
            if md_items:
                b["items"] = md_items
        if isinstance(headers, list) and headers and isinstance(raw_rows, list):
            hdr = " | ".join(str(h).strip() for h in headers if str(h).strip())
            piped = [_table_row_to_pipe(r) for r in raw_rows]
            piped = [p for p in piped if p]
            if hdr and piped:
                b["items"] = [hdr, *piped]
        elif isinstance(raw_rows, list) and raw_rows:
            if raw_rows and all(isinstance(r, dict) for r in raw_rows):
                skip = frozenset({"source_indices", "tags", "type", "id"})
                keys = [k for k in raw_rows[0] if k not in skip]
                if keys:
                    hdr = " | ".join(str(k).replace("_", " ") for k in keys)
                    body = [
                        " | ".join(str(r.get(k, "")).strip() for k in keys)
                        for r in raw_rows
                    ]
                    b["items"] = [hdr, *body]
            if not b.get("items"):
                piped = [_table_row_to_pipe(r) for r in raw_rows]
                piped = [p for p in piped if p]
                if piped:
                    b["items"] = piped
        if not b.get("items") and b.get("body"):
            md_items = _markdown_table_to_items(str(b["body"]))
            if md_items:
                b["items"] = md_items
        if (
            not b.get("items")
            and isinstance(data_val, str)
            and data_val.strip()
        ):
            md_items = _markdown_table_to_items(data_val)
            if md_items:
                b["items"] = md_items
        if b.get("items") and isinstance(b["items"], list):
            coerced: list[str] = []
            for row in b["items"]:
                piped = _table_row_to_pipe(row)
                if piped:
                    coerced.append(piped)
            if coerced:
                b["items"] = coerced

    # If model put a list into body only, split to items for list-like types
    if b["type"] in ("key_points", "steps") and not b.get("items") and b.get("body"):
        parts = re.split(r"[\n;•]+", str(b["body"]))
        cleaned = [p.strip(" -*\t") for p in parts if p.strip(" -*\t")]
        if len(cleaned) >= 2:
            b["items"] = cleaned
            # keep body as short intro optional — clear to avoid duplicate
            b.pop("body", None)

    if b["type"] in ("progress", "chart", "metrics") and not b.get("items"):
        data_val = b.get("data")
        if isinstance(data_val, list):
            coerced = _as_str_list(data_val)
            if coerced:
                b["items"] = coerced

    if b["type"] == "flow_diagram":
        nodes_out: list[dict[str, str]] = []
        node_ids: set[str] = set()
        raw_nodes = b.get("nodes")
        if isinstance(raw_nodes, list):
            for i, x in enumerate(raw_nodes):
                if not isinstance(x, dict):
                    continue
                nid = str(x.get("id") or x.get("label") or f"node_{i}").strip()
                label = str(x.get("label") or x.get("id") or "").strip()
                if not nid or not label or nid in node_ids:
                    continue
                node: dict[str, str] = {"id": nid, "label": label[:120]}
                detail = x.get("detail") or x.get("description") or x.get("example")
                if detail:
                    node["detail"] = _clean_display_text(str(detail).strip())[:400]
                nodes_out.append(node)
                node_ids.add(nid)

        edges_out: list[dict[str, str]] = []
        seen_edges: set[tuple[str, str, str]] = set()
        raw_edges = b.get("edges")
        if isinstance(raw_edges, list):
            for x in raw_edges:
                if not isinstance(x, dict):
                    continue
                src = str(x.get("source") or x.get("from") or "").strip()
                tgt = str(x.get("target") or x.get("to") or "").strip()
                if not src or not tgt or src not in node_ids or tgt not in node_ids:
                    continue
                label = str(x.get("label") or "").strip()[:120]
                key = (src, tgt, label)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edge: dict[str, str] = {"source": src, "target": tgt}
                if label:
                    edge["label"] = label
                edges_out.append(edge)

        if len(nodes_out) >= 2 and edges_out:
            b["nodes"] = nodes_out
            b["edges"] = edges_out
        else:
            b["nodes"] = None
            b["edges"] = None

    if b["type"] == "sequence_diagram":
        actors_out: list[str] = []
        raw_actors = b.get("actors")
        if isinstance(raw_actors, list):
            actors_out = [str(a).strip()[:60] for a in raw_actors if str(a).strip()]

        messages_out: list[dict[str, Any]] = []
        raw_messages = b.get("messages")
        if isinstance(raw_messages, list):
            for i, x in enumerate(raw_messages[:24]):
                if not isinstance(x, dict):
                    continue
                src = str(x.get("source") or x.get("from") or "").strip()[:60]
                tgt = str(x.get("target") or x.get("to") or "").strip()[:60]
                label = str(x.get("label") or x.get("text") or "").strip()
                if not src or not tgt or not label:
                    continue
                for actor in (src, tgt):
                    if actor not in actors_out:
                        actors_out.append(actor)
                order = x.get("order")
                try:
                    order = int(order)
                except (TypeError, ValueError):
                    order = i
                message: dict[str, Any] = {
                    "source": src,
                    "target": tgt,
                    "label": label[:120],
                    "order": order,
                }
                note = x.get("note") or x.get("detail") or x.get("example")
                if note:
                    message["note"] = _clean_display_text(str(note).strip())[:400]
                messages_out.append(message)

        actors_out = actors_out[:8]
        messages_out = [
            m for m in messages_out if m["source"] in actors_out and m["target"] in actors_out
        ]

        if len(actors_out) >= 2 and messages_out:
            b["actors"] = actors_out
            b["messages"] = messages_out
        else:
            b["actors"] = None
            b["messages"] = None

    # Drop blocks with no renderable content
    has_content = bool(
        b.get("body")
        or b.get("items")
        or b.get("terms")
        or b.get("faqs")
        or b.get("nodes")
        or b.get("actors")
    )
    if b.get("items") and isinstance(b["items"], list):
        b["items"] = [
            _clean_display_text(str(x))
            for x in b["items"]
            if str(x).strip() and not _is_separator_text(str(x))
        ]

    if not has_content:
        return None

    # source indices aliases
    si = b.get("source_indices") or b.get("sources") or b.get("citations") or b.get("refs")
    if si is not None:
        b["source_indices"] = si

    return b