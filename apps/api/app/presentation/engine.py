"""Build generative UI specs from agent context (workspace-agnostic)."""

from __future__ import annotations

import json
import re
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
from app.presentation.context import PresentationContext
from app.presentation.layout import layout_components_from_goal
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

    structured = ctx.structured_content or extract_structured_content(
        answer,
        goal=goal,
    )
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
                chunk_id="",
                document_id="",
                filename=name,
                score=None,
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
            resp = _client().chat.completions.create(
                model=render_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
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
        blocks = _ensure_requested_layout(blocks, layout_components, answer=answer)

    blocks = _normalize_qualitative_progress(blocks, answer=answer)

    blocks = _sanitize_blocks_for_grounding(
        blocks,
        answer=answer,
        context=grounding_context,
    )

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