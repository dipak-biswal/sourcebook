# Career Switch Plan — 8 Weeks | AI Engineer Path

> **Purpose:** Strategy, stack lock, salary, topics.  
> **Product / portfolio app:** **Sourcebook** (repo folder: `sourcebook`)  
> **Hands-on build:** Follow **`GREENFIELD_APP_ROADMAP.md`** (Week 0 → 8, one slice at a time).  
> **Future Grok sessions:** Read **this file + GREENFIELD_APP_ROADMAP.md**. Coach **one step at a time**.  
> **Reference only:** `agent-docs` monorepo + `BUILD_GUIDE.md` (old codebase study — not the portfolio to ship).  
> **Last decision lock date:** 2026-07-09  

---

## DECISION LOCK (do not reopen every session)

### Product name: **Sourcebook**  
### Portfolio repo: **`sourcebook`** (new greenfield git repo — not `agent-docs`)  
### Backend choice: **Python + FastAPI**

| Layer | Choice | Why |
|--------|--------|-----|
| **Backend** | **Python + FastAPI** | AI Engineer job posts list Python / FastAPI / LangChain far more than Next API routes |
| **Frontend** | **React** (you already know) | Demo UI only — do not re-learn FE |
| **Not primary backend** | Next.js Route Handlers | Fine for product FS roles; **weaker match** for “AI Engineer” ATS/JDs |

**Rule for 8 weeks:** One backend only. Python. No “maybe also Next backend.”

**You already know both** → pick the one that matches **AI Engineer hiring language**. That is **Python**.

---

## 0. Profile

| Field | Value |
|--------|--------|
| Company | Persistent Systems (India) |
| Designation | Senior Engineering Lead |
| Work style | **IC** (coding), not people manager |
| Experience | ~8.5 years |
| Strengths | **React** + prior **Python** time invested |
| CTC | **₹28.5 LPA** |
| Goal | Crack a job in **~2 months** |
| Hours | **~48 hrs/week** |
| Target geo | Remote **US / Europe / Middle East** (India product as backup) |

### Roles to apply (in priority order)

1. **AI Engineer** / **GenAI Engineer**  
2. **AI Application Engineer** / **LLM Engineer**  
3. **Software Engineer – AI / LLM**  
4. **Full-Stack AI Engineer** (React + Python AI API)  
5. Backup: Senior Full-Stack / Senior FE with AI in JD  

**Not primary:** ML Research, Eng Manager, pure Data Scientist  

### Salary targets

| Scenario | Target |
|----------|--------|
| Remote ask | **$100k–$120k** |
| Remote good | **$85k–$110k** |
| Remote floor | **~$80k** |
| India product backup | **₹42–55 LPA** |

### Interview one-liner

> Senior IC with 8.5 years React. I built **Sourcebook** — a multi-tenant document AI product (FastAPI + React): RAG with citations, streaming chat, and tool-using agents with approvals. Designation is Senior Engineering Lead; day-to-day I’m hands-on IC, not a people manager.

---

## 1. Locked tech stack (8 weeks)

```
Backend:      Python 3.11+ · FastAPI · Pydantic · Uvicorn
DB:           PostgreSQL · SQLAlchemy or Prisma-equivalent (SQLModel/SQLAlchemy) · Alembic
Vectors:      pgvector OR Chroma / Pinecone (one is enough)
AI core:      OpenAI + Anthropic APIs
Orchestration: LangGraph (primary) · LangChain only as needed
Frontend:     React (Vite or Next UI-only) — call Python API
Auth:         JWT or Clerk (simple, working)
Deploy:       Railway / Render / Fly.io for API · Vercel for React
Extras:       Docker (basic), Redis optional for chat history
```

### Explicitly skip (8 weeks)

- Training models / PyTorch deep dive  
- NestJS / Next as main backend  
- Multiple agent frameworks (CrewAI + AutoGen + …)  
- Kubernetes  
- Microservices sprawl  

**One agent stack:** LangGraph tool-calling loops.

---

## 2. Why this backend decision (for job in 2 months)

| Factor | Python/FastAPI | Next.js API as backend |
|--------|----------------|-------------------------|
| “AI Engineer” JD language | **Strong match** | Weak / rare |
| LangChain / LangGraph ecosystem | **Native** | Secondary |
| Your prior investment | Already spent time | Also strong |
| FE for demos | Pair with React | All-in-one |
| Full-stack product JD | Good if API + React | Stronger |
| **Goal = AI Engineer job** | **Winner** | Not primary |

**Conclusion:** To **crack AI Engineer–style roles in 2 months**, backend = **Python/FastAPI**.  
React is your advantage for **Full-Stack AI** demos, not your backend learning track.

---

## 3. North-star (end of week 8)

**Ship Sourcebook** so you can apply with confidence when:

1. **Live Python API** — auth + multi-tenant docs + Postgres  
2. **Live RAG** — ingest → embed → retrieve → answer + **citations**  
3. **Live agent** — tools, max steps, traces, at least one approval gate  
4. **React UI** (streaming chat + documents)  
5. 5-minute architecture explanation for **Sourcebook**  
6. Applications running for **weeks 5–8** (not only week 8)  
7. Public GitHub repo **`sourcebook`** + demo video

---

## 4. Time budget

| Week type | Build | Apply / interview prep |
|-----------|--------|-------------------------|
| Weeks 1–4 | ~42–44 hrs | ~4–6 hrs (prep notes) |
| Weeks 5–8 | ~30–34 hrs | **~14–18 hrs apply + polish** |

**~48 hrs/week total.**

---

# 8-WEEK ROADMAP

## WEEK 1 — FastAPI + Postgres fundamentals

**Outcome:** Deployed CRUD API + simple React form hitting it.

### Topics
- [ ] FastAPI routes, dependencies, status codes  
- [ ] Pydantic request/response models  
- [ ] Project structure (`app/main.py`, `routers`, `models`, `schemas`, `db`)  
- [ ] PostgreSQL + SQLAlchemy/SQLModel + migrations  
- [ ] JWT or simple auth (protected routes)  
- [ ] CORS for React dev server  
- [ ] Deploy API (Railway/Render)

### Project P0 — Task API
- Users + Tasks (or Notes)  
- CRUD, ownership checks  
- OpenAPI docs at `/docs`  
- React minimal UI optional but recommended  

**Done when:** live API URL + auth + your data only.

### Day plan (approx)
| Day | Focus |
|-----|--------|
| 1–2 | FastAPI hello, structure, Pydantic |
| 3–4 | DB models, CRUD |
| 5 | Auth |
| 6 | Deploy + React call |
| 7 | Harden errors, README |

---

## WEEK 2 — LLM API + streaming chat

**Outcome:** Chat endpoint streams tokens; React shows stream.

### Topics
- [ ] OpenAI/Anthropic SDK in Python  
- [ ] Chat messages schema (system/user/assistant)  
- [ ] Streaming responses (SSE) from FastAPI  
- [ ] Persist conversations in Postgres  
- [ ] Token/cost logging (simple table or log line)  
- [ ] Prompt basics: system prompt, history window  

### Project P1a — Chat API
- `POST /chat` streaming  
- Conversation history  
- React chat page  

**Done when:** live streaming chat with history.

---

## WEEK 3 — RAG (core AI Engineer skill)

**Outcome:** “Chat with my docs” with citations.

### Topics
- [ ] Chunking (size, overlap)  
- [ ] Embeddings  
- [ ] Vector store + **userId filter** (multi-tenant)  
- [ ] Retrieve top-k → build prompt → generate  
- [ ] Citations in response  
- [ ] Mini eval: 10–15 questions pass/fail  
- [ ] Failure modes: empty retrieval, bad chunks, hallucination  

### Project P1 — DocPilot (RAG)
```
Upload/paste → chunk → embed → store
Question → retrieve → answer + sources → stream to React
```

**Done when:** grounded answers + sources on production.

---

## WEEK 4 — Agents (LangGraph)

**Outcome:** Tool-calling agent with limits and audit log.

### Topics
- [ ] Tool definitions (schema + Python functions)  
- [ ] Agent loop / LangGraph state  
- [ ] max steps, timeouts, error feedback to model  
- [ ] Human approval for write actions  
- [ ] Persist `AgentRun` + `AgentStep`  
- [ ] When **not** to use an agent  

### Project P2 — ActionAgent
Tools (example): `search_docs`, `list_tasks`, `create_task`, `update_task`  
- React UI shows steps/tools  
- Demo video 2–3 min  

**Done when:** multi-step tool use visible + safe writes.

---

## WEEK 5 — Production hardening + system design

### Topics
- [ ] Rate limiting concept  
- [ ] Prompt injection awareness  
- [ ] Structured logging  
- [ ] Env/secrets, Docker basic  
- [ ] Background job concept for large ingest  
- [ ] System design drills (Section 9)  

### Work
- Polish P1 + P2  
- Architecture diagrams in READMEs  
- One-page “how it works” per project  

**Start applying lightly this week.**

---

## WEEK 6–7 — Apply hard + interview loops

### Apply targets (examples)
- AI Engineer, GenAI Engineer, LLM Engineer  
- AI Application Engineer  
- Full-Stack AI (React + Python)  
- Remote worldwide / contractor / EOR  

### Cadence
- **10–15 quality applications / day** on heavy days  
- Prep: RAG explain, agent explain, FastAPI vs Flask, SQL, React integration  
- Mock: “Walk me through a user message end-to-end”  

### Stories ready
- Senior IC ownership (not manager)  
- Why Python for AI backend  
- Tradeoffs: agent vs RAG vs single LLM call  

---

## WEEK 8 — Offers / gaps / second jump prep

- Fix anything interviewers poked  
- Optional stretch: hybrid search, better evals, Redis history  
- Notice period plan (60–90 days common)  
- Negotiate using salary table above  

---

# 5. Master topic checklist

## Backend (Python)
- [ ] FastAPI  
- [ ] Pydantic  
- [ ] Async basics if you use async routes  
- [ ] Postgres + ORM + migrations  
- [ ] AuthN / AuthZ  
- [ ] REST design  
- [ ] SSE streaming  
- [ ] Docker basics  
- [ ] Deploy + env vars  

## AI (must for AI Engineer JD)
- [ ] LLM APIs  
- [ ] Prompt / context engineering  
- [ ] Embeddings + vectors  
- [ ] RAG pipeline  
- [ ] Evals (small golden set)  
- [ ] Tool calling  
- [ ] LangGraph agent  
- [ ] Guardrails / HITL  
- [ ] Cost + latency awareness  
- [ ] Observability of runs  

## Frontend (light)
- [ ] React chat UI + streaming consumer  
- [ ] Auth header / session to API  
- [ ] Loading / error / empty states  

## System design (memorize flows)

### RAG
```
Doc → chunk → embed → vector DB
Q → embed → top-k (filter user) → prompt → LLM → stream + citations
```

### Agent
```
Goal → model → tool? → execute (validate, authz) → observe → loop → final
```

### Comparison
| Pattern | Use when |
|---------|----------|
| Code / SQL | Deterministic business rules |
| Single LLM | Draft, classify, short generate |
| RAG | Private or fresh knowledge |
| Agent | Multi-step + tools / side effects |

---

# 6. Things to remember

- **Backend = Python/FastAPI** for this roadmap (locked).  
- React = demo + full-stack AI story, not second backend.  
- AI Engineer ≠ train GPT; AI Engineer = **ship systems around models**.  
- Services “Lead” title → sell **senior IC + ownership**.  
- Apply from **week 5**, not after “perfect.”  
- First offer can be bridge; production AI on resume unlocks next jump.  

### Glossary
| Term | Meaning |
|------|---------|
| RAG | Retrieve docs then generate |
| Embedding | Vector for semantic search |
| Tool calling | Model asks your code to run a function |
| LangGraph | Graph/state machine for agent flows |
| Hallucination | Model invents facts |
| HITL | Human approves risky actions |
| SSE | Server-Sent Events (streaming) |

---

# 7. Progress tracker

| Week | Focus | Shipped? | Applications? |
|------|--------|----------|----------------|
| 1 | FastAPI + DB | [ ] | — |
| 2 | Streaming chat | [ ] | — |
| 3 | RAG | [ ] | — |
| 4 | Agent | [ ] | light prep |
| 5 | Harden + design | [ ] | start |
| 6 | Apply | polish | heavy |
| 7 | Apply + interviews | — | heavy |
| 8 | Close / fix gaps | — | heavy |

---

# 8. Instructions for future AI sessions

1. Read **`GREENFIELD_APP_ROADMAP.md` first** (what to build), then **this file** (strategy).  
2. Product is **Sourcebook**; repo folder **`sourcebook`**.  
3. Guide **one week-slice / step at a time**. Do not dump a full week unless asked.  
4. **Backend = Python/FastAPI.** Do not switch to Next-as-backend.  
5. **Do not treat `agent-docs` as the portfolio to ship** unless user explicitly reverts the greenfield plan.  
6. Help implement/debug/explain inside the **sourcebook** path the user provides.  
7. No LinkedIn drafts unless asked.  
8. Align with **~8 week job target** and salary bands above.  

---

# 9. Relationship between repos

| Repo | Role |
|------|------|
| **`sourcebook`** (new) | **Portfolio product to build and ship** |
| **`agent-docs`** (this Desktop folder) | Plans + optional reference for RAG/agent patterns |
| `BUILD_GUIDE.md` | Legacy step guide for studying **agent-docs** — secondary |
| `GREENFIELD_APP_ROADMAP.md` | **Primary build roadmap for Sourcebook** |
| `30_day_fullstack_ai_guide.md` | Optional deep-dive of old agent-docs code |

**Career strategy:** this file.  
**Build Sourcebook:** `GREENFIELD_APP_ROADMAP.md`.

---

# 10. Start Sourcebook (Week 0)

```bash
mkdir -p ~/projects/sourcebook && cd ~/projects/sourcebook
git init
mkdir -p apps/api apps/web docs
```

**New session prompt:**

```text
Read GREENFIELD_APP_ROADMAP.md and CAREER_SWITCH_30_DAY_PLAN.md.
Product: Sourcebook. Repo path: <FULL_PATH>/sourcebook
Start Week 0 skeleton — one step at a time.
```

**Week 0 done when:** FastAPI `/health`, React shell, Postgres + Redis via Docker, first commit.

---

*Decision locked: **Sourcebook** · Python/FastAPI · React · 8 weeks · greenfield repo `sourcebook`.*
