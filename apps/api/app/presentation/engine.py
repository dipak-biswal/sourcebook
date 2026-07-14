"""Build generative UI specs from agent context (workspace-agnostic)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agents.gen_ui import (
    GenUIBlock,
    GenerativeUIPayload,
    SourceSnippet,
    _normalize_block_dict,
)
from app.config import settings
from app.ingestion.retrieve import retrieve_chunks
from app.models import Document
from app.presentation.context import PresentationContext
from app.presentation.evidence import format_agent_evidence
from app.presentation.layout import format_layout_requirements, layout_components_from_goal
from app.usage import estimate_tokens, log_usage

_PLACEHOLDER_ORG = re.compile(
    r"(?i)(?:"
    r"xyz\s*corp(?:oration)?|abc\s*inc(?:orporated)?|def\s*ltd|ghi\s*co|"
    r"example\s+company|sample\s+company|test\s+company|placeholder\s+"
    r")"
)

_BLOCK_TYPES = (
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
)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)


def _corpus_blob(answer: str, context: str) -> str:
    return f"{answer}\n{context}".lower()


def _looks_like_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER_ORG.search(text))


def _phrase_grounded(phrase: str, corpus: str) -> bool:
    """True when a proper-noun phrase appears supported by answer/excerpts."""
    phrase = (phrase or "").strip()
    if not phrase or _looks_like_placeholder(phrase):
        return False
    tokens = [w for w in re.findall(r"[a-z0-9][a-z0-9+.#-]*", phrase.lower()) if len(w) > 2]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in corpus)
    return hits >= max(1, len(tokens) // 2)


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
) -> list[GenUIBlock]:
    """Add minimal fallback blocks when the model skipped requested component types."""
    if not required:
        return blocks
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
        out.append(
            GenUIBlock(
                type="chips",
                title="Themes",
                items=["Technical|technical", "Leadership|leadership", "Gaps|gaps"],
            )
        )
    elif "chips" in present:
        for i, b in enumerate(out):
            if b.type == "chips" and b.items and len(b.items) < 3:
                extra = ["Leadership|leadership", "Gaps|gaps"]
                merged = list(b.items)
                for e in extra:
                    if e not in merged:
                        merged.append(e)
                out[i] = b.model_copy(update={"items": merged[:5]})

    return out


def _numeric_stated_in_answer(value: str, answer: str) -> bool:
    v = value.rstrip("%").strip()
    if not v.isdigit():
        return False
    return v in answer or f"{v}%" in answer


def _infer_qualitative_level(label: str, answer: str) -> str:
    """Map a skill label to a level using wording in the agent answer."""
    lower = answer.lower()
    lbl = label.lower()
    gap_terms = ("ai depth", "backend", "leadership", "machine learning")
    if any(t in lbl for t in gap_terms):
        if any(
            g in lower
            for g in (
                "gap",
                "lacking",
                "lacks",
                "weakness",
                "foundational understanding",
                "further depth",
            )
        ):
            return "Gap"
    if "frontend" in lbl and "strong" in lower:
        return "Strong"
    if "ai" in lbl and any(
        w in lower for w in ("expanding", "foundational", "hands-on", "rag")
    ):
        return "Growing"
    if "testing" in lbl or "optimization" in lbl:
        if "proficient" in lower:
            return "Strong"
    if "domain" in lbl or "experience" in lbl:
        return "Moderate"
    if "strong" in lower:
        return "Strong"
    return "Moderate"


def _normalize_qualitative_progress(
    blocks: list[GenUIBlock],
    *,
    answer: str,
) -> list[GenUIBlock]:
    """Replace invented numeric scores with qualitative levels from the answer."""
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
            if re.match(r"^\d{1,3}%?$", val) and not _numeric_stated_in_answer(
                val, answer
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


def _workspace_context_lines(ctx: PresentationContext) -> str:
    lines: list[str] = []
    if ctx.workspace_name:
        lines.append(f"Workspace: {ctx.workspace_name}")
    if ctx.workspace_description.strip():
        lines.append(f"Workspace notes: {ctx.workspace_description.strip()}")
    if ctx.workspace_tags:
        lines.append(f"Tags: {', '.join(ctx.workspace_tags)}")
    if ctx.document_filenames:
        preview = ", ".join(ctx.document_filenames[:8])
        lines.append(f"Documents in workspace: {preview}")
    return "\n".join(lines) if lines else "Workspace: (no extra metadata)"


def build_presentation(
    db: Session,
    ctx: PresentationContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Produce a generative_ui payload from agent goal + answer + workspace context.
    Uses RAG chunks for grounding; layout is chosen freely from registered block types.
    """
    goal = (ctx.goal or "").strip()
    answer = (ctx.final_answer or "").strip()
    if not goal or not answer:
        return {"error": "goal and final_answer are required"}, {}

    query = f"{goal}\n{answer[:1500]}".strip()
    hits = retrieve_chunks(
        db,
        workspace_id=ctx.workspace_id,
        query=query,
        top_k=12,
        min_score=settings.rag_min_score,
        user_id=ctx.user_id,
        usage_meta={"source": "presentation", "goal": goal[:200]},
    )
    if not hits:
        hits = retrieve_chunks(
            db,
            workspace_id=ctx.workspace_id,
            query=goal or "overview summary",
            top_k=8,
            min_score=0.05,
            user_id=ctx.user_id,
            usage_meta={"source": "presentation_fallback", "goal": goal[:200]},
        )

    source_files: list[str] = []
    seen_files: set[str] = set()
    sources: list[SourceSnippet] = []
    context_parts: list[str] = []

    for i, (ch, score) in enumerate(hits, start=1):
        doc = db.get(Document, ch.document_id)
        name = doc.filename if doc else "document"
        if name not in seen_files:
            seen_files.add(name)
            source_files.append(name)
        snippet = (ch.content or "")[:280]
        sources.append(
            SourceSnippet(
                index=i,
                chunk_id=str(ch.id),
                document_id=str(ch.document_id),
                filename=name,
                score=round(float(score), 4) if score is not None else None,
                snippet=snippet,
            )
        )
        context_parts.append(f"[{i}] ({name}, score={score:.3f})\n{ch.content}")

    context = "\n\n".join(context_parts) if context_parts else "(no document excerpts)"
    agent_evidence_text = format_agent_evidence(ctx.agent_evidence)
    grounding_context = (
        f"{agent_evidence_text}\n\n{context}".strip()
        if agent_evidence_text
        else context
    )
    max_idx = len(sources)
    ws_lines = _workspace_context_lines(ctx)
    layout_components = layout_components_from_goal(goal)
    layout_section = format_layout_requirements(layout_components)
    agent_evidence_section = (
        f"\n{agent_evidence_text}\n"
        if agent_evidence_text
        else "\n(No agent tool evidence captured — use AGENT TEXT ANSWER and EXCERPTS only.)\n"
    )

    prompt = f"""You are the VISUAL SUMMARY layout engine. The agent already wrote a text answer for the Answer tab.
Your job: turn that answer (+ excerpts) into structured UI blocks. Do NOT repeat the answer as plain prose only.

WORKSPACE CONTEXT:
{ws_lines}

USER GOAL (layout intent — which components to build):
{goal}

{layout_section}

AGENT TEXT ANSWER (facts only — source material for blocks, NOT layout instructions):
{answer[:8000]}
{agent_evidence_section}
REGISTERED COMPONENTS (type field): {", ".join(_BLOCK_TYPES)}

GROUNDING RULES (MANDATORY):
- NEVER invent employers, job titles with fake companies, dates, projects, scores, or metrics.
- NEVER use placeholder names (XYZ Corp, ABC Inc, DEF Ltd, GHI Co, Acme, Example Company, etc.).
- Prefer facts from AGENT TOOL EVIDENCE and AGENT TEXT ANSWER; use EXCERPTS as supplemental workspace context.
- timeline: ONLY if AGENT TEXT ANSWER, AGENT TOOL EVIDENCE, or EXCERPTS list explicit roles/dates/employers. If unclear, OMIT timeline entirely.
- progress/chart: use qualitative levels (Strong, Growing, Foundational, Gap, Moderate) — NEVER invent numeric percentages unless the answer explicitly states that number for that skill.
- If the user requests a component but grounded data is missing, SKIP that block — do not fabricate filler.
- Rephrase and structure existing facts; do not hallucinate new ones.

CONTEXT → COMPONENT MAP (use at least 3 DIFFERENT types; avoid summary+key_points+chips only):
- Resume / profile / skills → progress (Skill | Strong/Growing/Gap) + chart (same qualitative levels) + chips + table
- Career / history → timeline ONLY with verbatim employers/dates from ANSWER/EXCERPTS; else use key_points or table
- Compare / gap analysis / vs → comparison (Aspect | Option A | Option B) OR table with header row
- Teach / explain concepts → key_terms + faq + steps (ordered items)
- Risks / caveats / important → callout (body required; use title like "Watch out")
- Memorable insight / testimonial line → quote (body=quote text, title=attribution or topic)
- Skill fit / readiness → progress or chart with qualitative levels (Label | Strong), not fake %
- Quick scan / themes → chips (items as "Theme|slug") + tag other blocks with matching tags: ["slug"]
- Process / how-to → steps (ordered items) — not bullets in key_points
- Narrative only → at most ONE summary block; pair with specialized types above

FIELD SHAPES:
- items: string list. Pipe-encoded rows for table/timeline/comparison/metrics:
  - table/comparison: "Col1 | Col2 | Col3" (first row may be headers)
  - metrics: "Label | Value" per item
  - timeline: "Period | Title | Detail" per item
  - progress/chart: "Label | Strong" or "Label | Growing" or "Label | Gap" (qualitative; numbers only if in answer)
  - chips: "Visible label|filter-slug" — tag related blocks with tags: ["filter-slug"]
- tags: optional string array on ANY block (lowercase slugs) for chip filtering
- key_terms: [{{"term":"","definition":""}}]
- faq: [{{"question":"","answer":""}}]
- callout/quote/summary: body text; title optional
- source_indices: 1-based excerpt refs (1..{max_idx}) or []

STRICT RULES:
- Include one block per requested component type when grounded (see REQUESTED UI COMPONENTS).
- Also add summary or key_points only if they add value — prefer specialized blocks.
- NEVER return only summary+key_points when the goal requests table/progress/chips/callout.
- Minimum blocks: max(3, number of requested component types).
- Return ONLY valid JSON (no markdown fences):
{{
  "title": "short title",
  "plain_summary": "2-4 sentence overview",
  "presentation_profile": "e.g. resume_dashboard, comparison_matrix, concept_guide",
  "blocks": [...]
}}

EXCERPTS:
{context}
"""

    try:
        resp = _client().chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a visual layout engine. Input: user goal (which widgets) "
                        "+ agent text answer (facts). Output: JSON UI blocks. "
                        "Build every requested component type with grounded content. "
                        "Never invent facts. Never put UI meta-text in blocks."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        raw = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        if usage is not None:
            log_usage(
                db,
                kind="presentation",
                model=settings.chat_model,
                user_id=ctx.user_id,
                workspace_id=ctx.workspace_id,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                meta={"goal": goal[:200]},
            )
        else:
            log_usage(
                db,
                kind="presentation",
                model=settings.chat_model,
                user_id=ctx.user_id,
                workspace_id=ctx.workspace_id,
                total_tokens=estimate_tokens(prompt, raw),
                meta={"goal": goal[:200], "estimated": True},
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

    blocks = _ensure_requested_layout(blocks, layout_components, answer=answer)

    blocks = _normalize_qualitative_progress(blocks, answer=answer)

    blocks = _sanitize_blocks_for_grounding(
        blocks,
        answer=answer,
        context=grounding_context,
    )

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
    build_meta: dict[str, Any] = {
        "prompt": prompt,
        "llm_output": raw,
        "model": settings.chat_model,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    if usage is not None:
        build_meta["prompt_tokens"] = usage.prompt_tokens
        build_meta["completion_tokens"] = usage.completion_tokens
        build_meta["total_tokens"] = usage.total_tokens
    else:
        prompt_est = estimate_tokens(prompt)
        completion_est = estimate_tokens(raw)
        build_meta["prompt_tokens"] = prompt_est
        build_meta["completion_tokens"] = completion_est
        build_meta["total_tokens"] = prompt_est + completion_est
    return out, build_meta