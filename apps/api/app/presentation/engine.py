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
from app.usage import estimate_tokens, log_usage

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
) -> dict[str, Any]:
    """
    Produce a generative_ui payload from agent goal + answer + workspace context.
    Uses RAG chunks for grounding; layout is chosen freely from registered block types.
    """
    goal = (ctx.goal or "").strip()
    answer = (ctx.final_answer or "").strip()
    if not goal or not answer:
        return {"error": "goal and final_answer are required"}

    query = f"{goal}\n{answer[:500]}".strip()
    hits = retrieve_chunks(
        db,
        workspace_id=ctx.workspace_id,
        query=query,
        top_k=8,
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
    max_idx = len(sources)
    ws_lines = _workspace_context_lines(ctx)

    prompt = f"""You design a visual UI spec from an agent answer. Pick components by CONTEXT — not a fixed card layout.

WORKSPACE CONTEXT:
{ws_lines}

USER GOAL:
{goal}

AGENT TEXT ANSWER:
{answer[:4000]}

REGISTERED COMPONENTS (type field): {", ".join(_BLOCK_TYPES)}

CONTEXT → COMPONENT MAP (use at least 3 DIFFERENT types; avoid summary+key_points+chips only):
- Resume / profile / skills → progress (Skill | 85 percent items) + chart (same shape, ranked bars) + chips (filter tags) + table
- Career / history / milestones → timeline (Period | Role | Detail per item) + callout for standout insight
- Compare / gap analysis / vs → comparison (Aspect | Option A | Option B) OR table with header row
- Teach / explain concepts → key_terms + faq + steps (ordered items)
- Risks / caveats / important → callout (body required; use title like "Watch out")
- Memorable insight / testimonial line → quote (body=quote text, title=attribution or topic)
- Skill fit / readiness / scores → progress or chart (Label | 0-100 or Label | 85%)
- Quick scan / themes → chips (items as "Theme|slug") + tag other blocks with matching tags: ["slug"]
- Process / how-to → steps (ordered items) — not bullets in key_points
- Narrative only → at most ONE summary block; pair with specialized types above

FIELD SHAPES:
- items: string list. Pipe-encoded rows for table/timeline/comparison/metrics:
  - table/comparison: "Col1 | Col2 | Col3" (first row may be headers)
  - metrics: "Label | Value" per item
  - timeline: "Period | Title | Detail" per item
  - progress/chart: "Label | 85" or "Label | 72%" (0-100 skill/fit scores)
  - chips: "Visible label|filter-slug" — tag related blocks with tags: ["filter-slug"]
- tags: optional string array on ANY block (lowercase slugs) for chip filtering
- key_terms: [{{"term":"","definition":""}}]
- faq: [{{"question":"","answer":""}}]
- callout/quote/summary: body text; title optional
- source_indices: 1-based excerpt refs (1..{max_idx}) or []

STRICT RULES:
- NEVER return 3+ blocks that are all summary, key_points, or chips — diversify.
- Include 4–7 blocks with substantive content.
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
                        "You output only JSON for a generative UI spec. "
                        "Pick diverse visual components based on goal context — "
                        "never default to generic summary+bullets+chips."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=2200,
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
        return {"error": f"Failed to generate presentation: {e}"}

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
        if len(blocks) >= 8:
            break

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
        return {"error": f"Invalid presentation shape: {e}", "raw": data}

    out = payload.model_dump()
    profile = data.get("presentation_profile")
    if isinstance(profile, str) and profile.strip():
        out["presentation_profile"] = profile.strip()[:120]
    out["version"] = 2
    return out