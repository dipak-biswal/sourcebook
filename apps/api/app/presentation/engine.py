"""Build generative UI specs from agent context (workspace-agnostic)."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.blocks import ALL_BLOCK_TYPES
from app.agents.gen_ui import (
    GenUIBlock,
    GenerativeUIPayload,
    SourceSnippet,
    _normalize_block_dict,
    parse_measure_item,
)
from app.config import settings
from app.presentation.context import PresentationContext
from app.presentation.layout import layout_components_from_goal
from app.presentation.llm_json import RENDER_PAYLOAD_SCHEMA, chat_json
from app.presentation.render_blocks import block_width, payload_from_assembly
from app.presentation.structured import (
    extract_structured_content,
    format_render_engine_prompt,
    summarize_agent_evidence,
)
from app.usage import estimate_tokens, log_usage

_PLACEHOLDER_ORG = re.compile(
    r"(?i)(?:"
    r"xyz\s*corp(?:oration)?|abc\s*inc(?:orporated)?|def\s*ltd|ghi\s*co|"
    r"example\s+company|sample\s+company|test\s+company|placeholder\s+"
    r")"
)
# Fake contact details and lorem-style filler that should never survive grounding.
_PLACEHOLDER_CONTACT = re.compile(
    r"(?i)(?:"
    r"\b[\w.+-]+@(?:example|test|email|domain)\.(?:com|org|net)\b|"
    r"\b(?:https?://)?(?:www\.)?example\.(?:com|org|net)\b|"
    r"\b(?:https?://)?(?:www\.)?test\.(?:com|org|net)\b|"
    r"\b(?:555[-.\s]?){1,2}\d{4}\b|"
    r"\b01[01][-/.]01[-/.](?:19|20)\d{2}\b|"
    r"\b(?:19|20)\d{2}[-/.]0?1[-/.]0?1\b|"
    r"\blorem\s+ipsum\b|"
    r"\bjohn\s+doe\b|\bjane\s+doe\b|"
    r"\bfoo\s+bar\b"
    r")"
)

_BLOCK_TYPES = ALL_BLOCK_TYPES


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _corpus_blob(answer: str, context: str) -> str:
    return f"{answer}\n{context}".lower()


def _looks_like_placeholder(text: str) -> bool:
    if not text or not text.strip():
        return False
    return bool(_PLACEHOLDER_ORG.search(text) or _PLACEHOLDER_CONTACT.search(text))


def _normalize_span(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _phrase_grounded(phrase: str, corpus: str) -> bool:
    """True when a proper-noun phrase is supported by a contiguous span in corpus.

    Half-token bag-of-words matching used to pass recombined facts ("Acme" +
    "Real" from different sentences). Require either an exact normalized
    substring of the full phrase, or an ordered contiguous window of its
    significant tokens.
    """
    phrase = (phrase or "").strip()
    if not phrase or _looks_like_placeholder(phrase):
        return False
    tokens = [w for w in re.findall(r"[a-z0-9][a-z0-9+.#-]*", phrase.lower()) if len(w) > 2]
    if not tokens:
        return True
    norm_phrase = _normalize_span(phrase)
    norm_corpus = _normalize_span(corpus)
    if norm_phrase and norm_phrase in norm_corpus:
        return True
    # Contiguous ordered window: all significant tokens appear in order with
    # only short gaps (≤2 intervening tokens) between consecutive ones.
    corpus_tokens = re.findall(r"[a-z0-9][a-z0-9+.#-]*", norm_corpus)
    if not corpus_tokens:
        return False
    start = 0
    for tok in tokens:
        found_at = -1
        # Search a limited lookahead from the previous match so tokens stay
        # near each other (recombined distant tokens fail).
        end = min(len(corpus_tokens), start + 3) if start > 0 else len(corpus_tokens)
        search_from = start if start > 0 else 0
        for i in range(search_from, end if start > 0 else len(corpus_tokens)):
            if corpus_tokens[i] == tok:
                found_at = i
                break
            # After the first token is locked, allow at most 2 intervening tokens.
            if start > 0 and i >= start + 2:
                break
        if found_at < 0:
            # First token may appear later — retry a full scan only for token 0.
            if start == 0:
                for i, ct in enumerate(corpus_tokens):
                    if ct == tok:
                        found_at = i
                        break
            if found_at < 0:
                return False
        start = found_at + 1
    return True


def _timeline_item_grounded(item: str, corpus: str) -> bool:
    if _looks_like_placeholder(item):
        return False
    org_match = re.search(r"\bat\s+(.+?)(?:\s*[—–-]\s*|\s*$)", item, re.I)
    if org_match:
        return _phrase_grounded(org_match.group(1).strip(), corpus)
    return _phrase_grounded(item, corpus)


def _bullet_lines(answer: str, limit: int = 8) -> list[str]:
    lines: list[str] = []
    for raw in answer.splitlines():
        line = raw.strip()
        if line.startswith(("-", "•", "*")):
            text = line.lstrip("-•* \t").strip()
            if text:
                lines.append(text)
    return lines[:limit]


def _ensure_requested_layout(
    blocks: list[GenUIBlock],
    required: list[str],
    *,
    answer: str,
    structured: dict[str, Any] | None = None,
) -> list[GenUIBlock]:
    """
    Add minimal fallback blocks when the model skipped requested component types.

    Fallbacks are grounded only: text quoted from the answer or themes already
    extracted into structured content. A component with no grounded data is
    omitted — never filled with invented placeholder content.
    """
    if not required:
        return blocks
    structured = structured if isinstance(structured, dict) else {}
    present = {b.type for b in blocks}
    out = list(blocks)

    if "callout" in required and "callout" not in present:
        lower = answer.lower()
        for needle in ("main gap", "gap:", "gaps:", "lacking", "weakness", "improve"):
            idx = lower.find(needle)
            if idx >= 0:
                snippet = answer[idx : idx + 320].strip()
                if len(snippet) > 24:
                    out.append(
                        GenUIBlock(
                            type="callout",
                            title="Main gap",
                            body=snippet,
                        )
                    )
                    break

    if "table" in required and "table" not in present:
        bullets = _bullet_lines(answer)
        if len(bullets) >= 2:
            rows = ["Point | Detail"] + [
                f"{b[:40]} | {b[40:120].strip() or '—'}" for b in bullets[:6]
            ]
            out.append(GenUIBlock(type="table", title="Key points", items=rows))

    if "chips" in required and "chips" not in present:
        themes = [
            str(t).strip()
            for t in (structured.get("themes") or [])
            if str(t).strip()
        ]
        if len(themes) >= 2:
            items = [
                f"{t.title()}|{re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')}"
                for t in themes[:5]
            ]
            out.append(GenUIBlock(type="chips", title="Themes", items=items))

    return out


def _numeric_stated_in_answer(value: str, answer: str) -> bool:
    v = value.rstrip("%").strip()
    if not v.isdigit():
        return False
    return v in answer or f"{v}%" in answer


_MEASURE_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _number_grounded(num: str, corpus: str) -> bool:
    """True when the digit string appears in the corpus (comma-insensitive)."""
    n = num.replace(",", "").lstrip("-")
    if not n:
        return False
    if n.endswith(".0"):
        n = n[:-2]
    return n in corpus


def _measure_numbers_grounded(value: str, corpus: str) -> bool:
    """Every numeric token in a measure value must appear in the corpus."""
    nums = _MEASURE_NUM_RE.findall(value)
    if not nums:
        return True  # qualitative value — nothing to verify
    return all(_number_grounded(n, corpus) for n in nums)


def _ground_metric_numbers(
    blocks: list[GenUIBlock],
    *,
    corpus: str,
) -> list[GenUIBlock]:
    """
    Drop metrics rows whose numbers are not stated in the answer or evidence.

    Metrics tiles present values as facts, so an unverifiable number is
    removed rather than softened; a block losing every row is dropped.
    """
    corpus = corpus.replace(",", "")
    out: list[GenUIBlock] = []
    for block in blocks:
        if block.type != "metrics" or not block.items:
            out.append(block)
            continue
        kept = [i for i in block.items if _measure_numbers_grounded(i, corpus)]
        if not kept:
            continue
        if len(kept) != len(block.items):
            block = block.model_copy(update={"items": kept})
        out.append(block)
    return out


def _attach_measures(blocks: list[GenUIBlock]) -> list[GenUIBlock]:
    """Derive structured {label, value, unit, numeric} rows for measure blocks."""
    out: list[GenUIBlock] = []
    for block in blocks:
        if block.type in ("metrics", "progress", "chart") and block.items:
            measures = [
                m
                for m in (parse_measure_item(i) for i in block.items)
                if m is not None
            ]
            if measures:
                block = block.model_copy(update={"measures": measures})
        out.append(block)
    return out


# Ordered by precedence: an explicit weakness statement beats praise elsewhere
# in the same sentence ("strong basics but lacks depth" → Gap).
_LEVEL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Gap",
        (
            "gap",
            "lacking",
            "lacks",
            "weakness",
            "weak",
            "missing",
            "needs improvement",
            "needs work",
            "further depth",
            "limited",
        ),
    ),
    (
        "Strong",
        (
            "strong",
            "expert",
            "excellent",
            "advanced",
            "proficient",
            "extensive",
            "deep",
            "mastery",
            "solid",
        ),
    ),
    (
        "Growing",
        (
            "growing",
            "improving",
            "expanding",
            "learning",
            "foundational",
            "emerging",
            "developing",
            "hands-on",
            "early",
        ),
    ),
)


def _infer_qualitative_level(label: str, answer: str) -> str:
    """
    Map a label to a level using the answer sentences that mention it.

    Domain-agnostic: no hardcoded label vocabulary — only wording the main
    agent actually wrote about this label. Unmentioned labels stay Moderate.
    """
    tokens = [t for t in re.findall(r"[a-z0-9]+", label.lower()) if len(t) > 2]
    if not tokens:
        return "Moderate"
    sentences = re.split(r"(?<=[.!?])\s+|\n+", answer)
    scoped = " ".join(
        s for s in sentences if any(t in s.lower() for t in tokens)
    ).lower()
    if not scoped:
        return "Moderate"
    for level, words in _LEVEL_KEYWORDS:
        if any(w in scoped for w in words):
            return level
    return "Moderate"


def _normalize_qualitative_progress(
    blocks: list[GenUIBlock],
    *,
    answer: str,
    corpus: str = "",
) -> list[GenUIBlock]:
    """
    Replace invented numeric scores with qualitative levels from the answer.

    corpus (answer + evidence snippets) widens the grounding check so a
    number stated only in a retrieved snippet still counts as stated.
    """
    grounding = corpus or answer
    out: list[GenUIBlock] = []
    for block in blocks:
        if block.type not in ("progress", "chart") or not block.items:
            out.append(block)
            continue
        new_items: list[str] = []
        for item in block.items:
            if "|" not in item:
                new_items.append(item)
                continue
            label, val = [p.strip() for p in item.split("|", 1)]
            if re.match(r"^\d{1,3}%?$", val) and not _number_grounded(
                val.rstrip("%"), grounding
            ):
                level = _infer_qualitative_level(label, answer)
                new_items.append(f"{label} | {level}")
            elif val.lower() in (
                "high",
                "medium",
                "low",
                "excellent",
                "good",
                "fair",
                "poor",
            ):
                mapping = {
                    "high": "Strong",
                    "excellent": "Strong",
                    "good": "Moderate",
                    "medium": "Moderate",
                    "fair": "Growing",
                    "low": "Gap",
                    "poor": "Gap",
                }
                new_items.append(f"{label} | {mapping.get(val.lower(), val)}")
            else:
                new_items.append(item)
        out.append(block.model_copy(update={"items": new_items}))
    return out


def _sanitize_blocks_for_grounding(
    blocks: list[GenUIBlock],
    *,
    answer: str,
    context: str,
) -> list[GenUIBlock]:
    """Drop or trim blocks that invent employers, roles, or placeholder facts."""
    corpus = _corpus_blob(answer, context)
    cleaned: list[GenUIBlock] = []

    for block in blocks:
        if block.type == "timeline" and block.items:
            grounded = [i for i in block.items if _timeline_item_grounded(i, corpus)]
            if not grounded:
                continue
            if len(grounded) != len(block.items):
                block = block.model_copy(update={"items": grounded})
        elif block.body and _looks_like_placeholder(block.body):
            continue
        cleaned.append(block)

    return cleaned


def _block_citation_text(block: GenUIBlock) -> str:
    parts: list[str] = [block.title or "", block.body or ""]
    parts.extend(block.items or [])
    for t in block.terms or []:
        parts.append(f"{t.term} {t.definition}")
    for f in block.faqs or []:
        parts.append(f"{f.question} {f.answer}")
    return " ".join(p for p in parts if p)


def _attribute_block_sources(
    blocks: list[GenUIBlock],
    sources: list[SourceSnippet],
) -> list[GenUIBlock]:
    """
    Attach snippet-overlap citations to blocks that carry none.

    The code-assembly path maps structured fields to blocks and cannot carry
    per-block citations; recover them by token overlap with source snippets.
    Conservative: a block with no clear overlap keeps zero citations rather
    than inheriting unrelated sources.
    """
    if not sources:
        return blocks
    snippet_tokens = [
        (s.index, set(re.findall(r"[a-z0-9]{4,}", (s.snippet or "").lower())))
        for s in sources
    ]
    out: list[GenUIBlock] = []
    for block in blocks:
        if block.source_indices:
            out.append(block)
            continue
        btoks = set(re.findall(r"[a-z0-9]{4,}", _block_citation_text(block).lower()))
        if len(btoks) < 3:
            out.append(block)
            continue
        matches: list[tuple[int, int]] = []
        for idx, stoks in snippet_tokens:
            if not stoks:
                continue
            common = btoks & stoks
            if len(common) >= 3 and len(common) >= 0.25 * min(len(btoks), len(stoks)):
                matches.append((len(common), idx))
        matches.sort(key=lambda m: (-m[0], m[1]))
        if matches:
            block = block.model_copy(
                update={"source_indices": [idx for _, idx in matches[:3]]}
            )
        out.append(block)
    return out


def _structured_grounding_corpus(
    structured: dict[str, Any],
    *,
    answer: str,
    evidence_summary: dict[str, Any],
) -> str:
    """Compact text corpus for post-render grounding when RAG excerpts are skipped."""
    parts = [answer, json.dumps(structured, ensure_ascii=False)]
    for hit in evidence_summary.get("document_snippets") or []:
        if isinstance(hit, dict):
            parts.append(hit.get("snippet") or "")
    return "\n".join(parts).lower()


def build_presentation(
    db: Session,
    ctx: PresentationContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Produce a generative_ui payload by executing an approved layout plan.

    Called from render_ui after plan_layout; requires layout_plan on the context.
    """
    goal = (ctx.goal or "").strip()
    answer = (ctx.final_answer or "").strip()
    if not goal or not answer:
        return {"error": "goal and final_answer are required"}, {}

    layout_plan = ctx.layout_plan if isinstance(ctx.layout_plan, dict) else None
    if not layout_plan:
        return {"error": "layout_plan is required — call plan_layout before render_ui"}, {}

    # Prefer the structured content already resolved by the orchestrator /
    # plan_layout. Only re-extract as a last resort for standalone callers.
    if isinstance(ctx.structured_content, dict) and ctx.structured_content:
        structured = ctx.structured_content
    else:
        structured = extract_structured_content(answer, goal=goal)
        ctx.structured_content = structured
    evidence_summary = summarize_agent_evidence(ctx.agent_evidence)

    source_files: list[str] = []
    sources: list[SourceSnippet] = []
    for i, hit in enumerate(ctx.agent_evidence.document_hits[:6], start=1):
        name = hit.filename or "document"
        if name not in source_files:
            source_files.append(name)
        sources.append(
            SourceSnippet(
                index=i,
                chunk_id=hit.chunk_id or "",
                document_id=hit.document_id or "",
                filename=name,
                score=hit.score,
                snippet=(hit.snippet or "")[:280],
            )
        )

    grounding_context = _structured_grounding_corpus(
        structured,
        answer=answer,
        evidence_summary=evidence_summary,
    )
    max_idx = len(sources)
    layout_components = layout_components_from_goal(goal)
    if isinstance(layout_plan.get("components"), list):
        layout_components = list(layout_plan["components"])

    # --- Code-first assembly (primary path) ---
    assembled_payload = payload_from_assembly(
        layout_plan=layout_plan,
        structured=structured if isinstance(structured, dict) else {},
        goal=goal,
        workspace_name=ctx.workspace_name,
        source_files=source_files,
    )
    render_fallback_used = False
    data: dict[str, Any]
    prompt = ""
    raw = ""
    render_model = "code_assembly"
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if assembled_payload and assembled_payload.get("blocks"):
        data = assembled_payload
        raw = json.dumps(assembled_payload, ensure_ascii=False)
        prompt = "CODE ASSEMBLY (no LLM) — blocks mapped from structured content via source_hint"
    else:
        # --- LLM fallback when assembly is empty ---
        render_fallback_used = True
        prompt = format_render_engine_prompt(
            layout_plan=layout_plan,
            structured_content=structured,
            evidence_summary=evidence_summary,
            workspace_name=ctx.workspace_name,
        )
        render_model = settings.visual_summary_model
        system_message = (
            "You execute an approved visual layout plan. "
            "Populate UI blocks from structured content only. "
            "Output valid JSON. Never invent facts."
        )
        try:
            resp = chat_json(
                _client(),
                model=render_model,
                system=system_message,
                prompt=prompt,
                schema_name="render_payload",
                schema=RENDER_PAYLOAD_SCHEMA,
                max_tokens=4000,
            )
            raw = (resp.choices[0].message.content or "").strip()
            usage = resp.usage
            if usage is not None:
                prompt_tokens = int(usage.prompt_tokens or 0)
                completion_tokens = int(usage.completion_tokens or 0)
                total_tokens = int(usage.total_tokens or 0)
                log_usage(
                    db,
                    kind="presentation",
                    model=render_model,
                    user_id=ctx.user_id,
                    workspace_id=ctx.workspace_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    meta={"goal": goal[:200], "render_fallback": True},
                )
            else:
                total_tokens = estimate_tokens(prompt, raw)
                log_usage(
                    db,
                    kind="presentation",
                    model=render_model,
                    user_id=ctx.user_id,
                    workspace_id=ctx.workspace_id,
                    total_tokens=total_tokens,
                    meta={"goal": goal[:200], "estimated": True, "render_fallback": True},
                )
            db.commit()
        except Exception as e:
            return {"error": f"Failed to generate presentation: {e}"}, {}

        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "title": goal[:80] or "Presentation",
                "plain_summary": answer[:500],
                "presentation_profile": "fallback_markdown",
                "blocks": [
                    {
                        "type": "summary",
                        "title": "Overview",
                        "body": answer[:2000],
                        "source_indices": [1] if sources else [],
                    }
                ],
            }

    plain = (
        data.get("plain_summary")
        or data.get("summary")
        or data.get("overview")
        or answer[:500]
    )

    raw_blocks = data.get("blocks") or data.get("sections") or data.get("components") or []
    if not isinstance(raw_blocks, list):
        raw_blocks = []

    blocks: list[GenUIBlock] = []
    for raw_b in raw_blocks[:10]:
        if isinstance(raw_b, GenUIBlock):
            blocks.append(raw_b)
            continue
        norm = _normalize_block_dict(raw_b)
        if not norm:
            continue
        btype = str(norm.get("type") or "summary")
        if btype not in _BLOCK_TYPES:
            norm["type"] = "summary" if norm.get("body") else "key_points"
        try:
            block = GenUIBlock.model_validate(norm)
        except Exception:
            continue
        if max_idx:
            block.source_indices = [i for i in block.source_indices if 1 <= i <= max_idx]
        blocks.append(block)
        if len(blocks) >= 10:
            break

    if render_fallback_used:
        blocks = _ensure_requested_layout(
            blocks,
            layout_components,
            answer=answer,
            structured=structured if isinstance(structured, dict) else {},
        )

    # Numbers may only come from what the main agent wrote or retrieved —
    # deliberately excludes the structured dump, which is what's being checked.
    numeric_corpus = " ".join(
        [
            answer,
            *(h.snippet or "" for h in ctx.agent_evidence.document_hits),
            *(h.snippet or "" for h in ctx.agent_evidence.web_hits),
        ]
    )

    blocks = _normalize_qualitative_progress(
        blocks, answer=answer, corpus=numeric_corpus
    )

    blocks = _ground_metric_numbers(blocks, corpus=numeric_corpus)

    blocks = _sanitize_blocks_for_grounding(
        blocks,
        answer=answer,
        context=grounding_context,
    )

    blocks = _attribute_block_sources(blocks, sources)

    blocks = _attach_measures(blocks)

    # Ensure every block carries a grid width hint (assembly path already sets it).
    blocks = [
        b if b.width else b.model_copy(update={"width": block_width(b)})
        for b in blocks
    ]

    if not blocks:
        blocks = [
            GenUIBlock(
                type="summary",
                title="Overview",
                body=answer[:1500],
                source_indices=[1] if sources else [],
            ),
        ]
        if len(answer) > 100:
            bullets = [line.strip("-• ") for line in answer.split("\n") if line.strip()][:6]
            if bullets:
                blocks.append(
                    GenUIBlock(
                        type="key_points",
                        title="Highlights",
                        items=bullets,
                        source_indices=[],
                    )
                )

    try:
        payload = GenerativeUIPayload(
            title=str(data.get("title") or goal)[:120],
            plain_summary=str(plain or "")[:2000],
            blocks=blocks,
            source_files=source_files,
            sources=sources,
        )
    except Exception as e:
        return {"error": f"Invalid presentation shape: {e}", "raw": data}, {}

    out = payload.model_dump()
    profile = data.get("presentation_profile")
    if isinstance(profile, str) and profile.strip():
        out["presentation_profile"] = profile.strip()[:120]
    out["version"] = 2
    assembly_meta = data.get("assembly_meta") if isinstance(data, dict) else None
    if not isinstance(assembly_meta, dict):
        assembly_meta = {
            "assembled_blocks": [b.type for b in blocks],
            "dropped_blocks": [],
            "render_fallback_used": render_fallback_used,
        }
    else:
        assembly_meta = {
            **assembly_meta,
            "render_fallback_used": render_fallback_used
            or bool(assembly_meta.get("render_fallback_used")),
        }
    out["assembly_meta"] = assembly_meta

    if render_fallback_used and total_tokens == 0 and prompt:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(raw)
        total_tokens = prompt_tokens + completion_tokens

    build_meta: dict[str, Any] = {
        "prompt": prompt,
        "llm_output": raw,
        "model": render_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "assembly_meta": assembly_meta,
    }
    return out, build_meta