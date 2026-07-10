# Sourcebook RAG eval — v1

**Product:** Sourcebook  
**Date:** 2026-07-10  
**Doc under test:** `vercel.design.md` (Vercel-inspired DESIGN.md; ingest until status **ready**)  
**Models (record what you used):**

| Role | Model |
|------|--------|
| Embeddings | e.g. `text-embedding-3-small` |
| Chat | e.g. `gpt-4o-mini` |

**Settings to note:** `RAG_TOP_K`, `RAG_MIN_SCORE` (defaults in `app/config.py` / `.env`)

---

## How to run (manual)

1. Log in → **Documents** → ensure `vercel.design.md` is **ready** (Ingest if needed).  
2. **Chat** → **New session**.  
3. Ask each question **exactly** (or close paraphrase).  
4. Mark **Pass / Fail** using criteria below.  
5. Optionally paste a short answer note (1 line).  

### Pass criteria

| Type | Pass if |
|------|---------|
| **Factual** | Answer matches doc (or correct paraphrase); sources shown when claiming doc facts |
| **Denial** | No invented doc facts; no sources (or clear “no match”); may say don’t know / no grounded match |
| **Partial** | States what is known from doc; does not invent missing details |

### Score

```text
Pass rate = (# Pass) / 12
Target for Week 3 “good enough”: ≥ 9/12 (75%)
```

---

## Eval sheet

| # | Type | Question | Expected (from doc) | Pass? | Notes |
|---|------|----------|---------------------|-------|-------|
| 1 | Factual | What is Vercel’s primary brand / ink color? | Near-black **#171717** (ink); not a brand-blue | ☐ | |
| 2 | Factual | What body / canvas background color is described? | Near-white **#fafafa** (or equivalent “near-white canvas”) | ☐ | |
| 3 | Factual | Which typefaces are used for headlines and technical labels? | **Geist** (display/sans) and **Geist Mono** (captions/labels) | ☐ | |
| 4 | Factual | What is the display font weight cap mentioned? | Weight **600** (not heavier display weights) | ☐ | |
| 5 | Factual | What letter-spacing is called out for large display type? | Aggressive tracking, e.g. **-2.4px** on large display | ☐ | |
| 6 | Factual | What colors make up the hero mesh gradient? | **Cyan / blue / magenta (pink) / amber** (e.g. #50e3c2, #007cf0, #ff0080, #f9cb28) | ☐ | |
| 7 | Factual | How should the mesh gradient be used? | **Hero scale only** — not miniaturized everywhere | ☐ | |
| 8 | Factual | What two pill button scales coexist? | **~100px** marketing CTAs and **~6px** nav-style pills; not mixed on one control | ☐ | |
| 9 | Factual | What does the doc say about a second accent / brand-blue? | **No** second brand-blue or soft marketing accent — ink *is* the brand | ☐ | |
| 10 | Factual | What shadow approach is preferred over heavy single drops? | **Stacked shadows** + inset hairline ring on cards | ☐ | |
| 11 | Denial | What is today’s weather in Bangalore? | Should **not** invent from design doc; **no sources** / denial path | ☐ | |
| 12 | Denial | Who won the 2018 FIFA World Cup according to this design system doc? | Off-topic; **denial / no grounded match**, no fake citations | ☐ | |

---

## Stretch questions (optional, not required for 12/12)

| # | Question | Expected |
|---|----------|----------|
| S1 | Name the Develop / Preview / Ship gradient pair idea. | Three-pair gradient stack (develop blue-cyan, preview purple-pink, ship red-amber) if present in tokens |
| S2 | About how many components does the DESIGN.md claim? | **40+** components |
| S3 | What is `display-xl` font size in the typography tokens? | **48px** (if retrieved) |

---

## Run log

| Field | Value |
|--------|--------|
| Runner | Dipak |
| Date run | 2026-07-10 |
| Pass count | **10 / 12** (after retest of Q5–Q6) |
| Pass rate | **83%** (target ≥ 75%) ✅ |
| Chat model | OpenAI (e.g. gpt-4o-mini) — confirm in Usage page |
| Embed model | text-embedding-3-small (confirm) |
| Notes | First pass 8/12; re-ask improved Q5–Q6. Denial OK. Message order fix applied in code. |

### Results detail

| # | Result | Notes |
|---|--------|--------|
| 1 | Pass | Primary ink #171717 |
| 2 | Pass | Canvas #fafafa |
| 3 | Pass | Geist + Geist Mono |
| 4 | Pass | Weight 600 cap |
| 5 | **Pass** (retest) | Correct large-display tracking after clearer ask / better hit |
| 6 | **Pass** (retest) | Hero mesh colors distinguished correctly |
| 7 | **Fail** | Re-score optional: hero-only + no miniaturize may already be Pass |
| 8 | Pass | 100px vs 6px pills |
| 9 | Pass | No second brand-blue |
| 10 | **Fail** | Optional re-score: stacked shadows + hairline may already be Pass |
| 11 | Pass | Off-topic denial |
| 12 | Pass | Off-topic denial |

### Failure analysis (fill after run)

| Failed # | Likely cause | Next experiment |
|----------|--------------|-----------------|
| 7 | Strict mark vs partial good answer | Re-read once; upgrade to Pass if criteria met |
| 10 | Strict mark vs near-correct shadow answer | Same — optional Pass if stacked + hairline present |
| 5–6 (resolved) | Ambiguous wording / competing sections | Clearer questions improved retrieval |

---

## After first run (quality loop)

1. Pick **up to 3** fails.  
2. Change **one** thing only (e.g. `RAG_MIN_SCORE` 0.18 vs 0.25, or chunk_size).  
3. Re-ingest if chunk settings changed.  
4. Retest only those 3 questions.  
5. Record before/after in Notes.

---

## Interview talking points

- Golden set of 12 questions with pass/fail, not vibes.  
- Includes **positive** grounded Qs and **negative** denial cases.  
- Single-variable experiments after failures.  
- Usage page + OpenAI dashboard for cost awareness.

---

*Week 3 A9 start — manual eval harness for Sourcebook.*
