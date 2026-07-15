"""Generative UI schema and block normalization for visual summaries."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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
]


class KeyTerm(BaseModel):
    term: str
    definition: str


class FaqItem(BaseModel):
    question: str
    answer: str


class GenUIBlock(BaseModel):
    type: BlockType
    title: str | None = None
    body: str | None = None
    items: list[str] | None = None
    terms: list[KeyTerm] | None = None
    faqs: list[FaqItem] | None = None
    # Lowercase slugs — matched by interactive chip filters in the web UI
    tags: list[str] | None = None
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


def _markdown_table_to_items(body: str) -> list[str]:
    rows: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        if re.match(r"^[\s\-:|]+$", line):
            continue
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if parts:
            rows.append(" | ".join(parts))
    return rows


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, list):
        out: list[str] = []
        for x in value:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                # {"text": "..."} or {"point": "..."}
                for k in ("text", "point", "item", "value", "content"):
                    if k in x and str(x[k]).strip():
                        out.append(str(x[k]).strip())
                        break
            else:
                t = str(x).strip()
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
    }
    b["type"] = type_map.get(t, t if t in {
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
    } else "summary")

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
        b["body"] = body.strip()

    # list aliases
    items = (
        b.get("items")
        or b.get("points")
        or b.get("bullets")
        or b.get("key_points")
        or b.get("steps")
        or b.get("list")
    )
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
                faqs_out.append({"question": str(q).strip(), "answer": str(a).strip()})
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
        raw_rows = b.get("rows") or b.get("data") or b.get("table")
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

    # Drop blocks with no renderable content
    has_content = bool(
        b.get("body")
        or b.get("items")
        or b.get("terms")
        or b.get("faqs")
        or b["type"] in ("chips", "table", "metrics", "progress", "chart")
    )
    if not has_content:
        return None

    # source indices aliases
    si = b.get("source_indices") or b.get("sources") or b.get("citations") or b.get("refs")
    if si is not None:
        b["source_indices"] = si

    return b