# Sourcebook

Multi-tenant **document AI workspace**: upload files, run an ingest pipeline (parse → chunk → embed), **chat with grounded answers and citations**, and run **tool-using agents** with human approval — including a **Visual Summary** pipeline that turns agent answers into generative UI.

> Not a toy chatbot — a small AI product with real backend concerns: tenancy, async jobs, rate limits, execution traces, and presentation handoff.

---

## What we've built to date

Honest snapshot of the product as of the current codebase.

### Done (shipped)

| Area | Status |
|------|--------|
| **Auth & tenancy** | Register / login (JWT + bcrypt); workspaces with membership (owner/member); all data scoped by `workspace_id` |
| **Workspace management** | Create, edit (name, **description**, **tags**), delete; workspace selector; Settings UI |
| **Documents & ingest** | Upload, list, delete; multi-format parse → chunk → embed; status lifecycle; Redis + **RQ** worker (or sync fallback) |
| **RAG chat** | Top-k retrieval → LLM answer with **SSE streaming**; citations (filename, score, snippet); denial when retrieval is empty/off-topic |
| **Retrieval quality** | **pgvector HNSW** embeddings (Alembic migrations) → **hybrid retrieval** (vector + full-text, RRF fusion) → **LLM reranking** of the fused pool |
| **Workspace-derived context** | `WorkspaceContextPacket` from name/description/tags/docs; injected into main agent prompt, handoff, and visual planner; derived-context **preview in Settings** with tag chips; de-biased generic prompts |
| **Conversations** | Create, list, delete; message history with citations; chat suggestions endpoint |
| **Chat ↔ Agent mode** | Same Chat page: RAG by default, or tool-using agent + HITL |
| **Main workspace agent** | Tools: `get_current_date`, `list_documents`, `search_documents`, `web_search`, `create_note` (HITL) |
| **Tool execution** | Date-first tool policy; **parallel read tools** (thread pool, max 4); write tools pause for approval |
| **HITL + resume** | `create_note` and **visual summary offer** pause for Approve / Reject; approve executes then **resumes** the loop with SSE |
| **Visual Summary (Phase A + B)** | After main agent answer → user can approve presentation → structured **handoff** → `plan_layout` (validate + optional replan) → `render_ui` → `presentation_spec` |
| **Visual Summary assembly** | **Code-first block assembly** (UiIntent skeleton) with **planner-LLM authority** over block selection/order/titles/width (grounded `source_hint` validation, code-skeleton fallback, `visual_summary_llm_planner` flag); dedupe + junk-block filtering |
| **Handoff (spine + v2 modules)** | Extract `summary`, `key_points`, `faq`, `sections`, `themes` (heuristic + LLM); fail if too thin; optional modules (`concepts`, `levels`, `matrix_rows`, `metrics`, `timeline`, …) + `presentation_hints` |
| **Generative UI** | Block library: summary, key points, key terms, FAQ, steps, callout, table, progress, chart, chips, timeline, comparison, metrics, quote; normalize on API + web |
| **Agent streaming & trace** | Live SSE (`llm_start` / `llm_end` / steps / status / done); LangSmith-style **trace tree** (main agent + Visual Summary subtree) |
| **Run panel UX** | Answer / **Visual summary** / Trace tabs; stay on Trace while running; Visual summary opt-in (no auto-switch) |
| **Notes** | Full CRUD; editor + sidebar; can be created via agent after HITL |
| **Usage & rate limits** | Token usage events + Usage page; per-user limits on chat / ingest / agent starts (Redis + in-memory fallback) |
| **Dashboard & settings** | Home stats/quick actions; profile, password, workspaces |
| **Product UI polish** | Light/dark theme; toasts, confirms, empty states, skeletons; onboarding checklist hooks |
| **Document storage** | S3-compatible object storage (**R2/B2**) behind a storage interface; local filesystem fallback |
| **Ops** | Structured logging + `X-Request-ID`; health endpoints; `DEV_MODE` panel; Swagger at `/docs`; production safety guards |
| **Deployment** | Live: web on **Vercel**, API on **Render**, Redis on **Upstash** |
| **Tests** | Backend unit tests for agents, presentation, handoff, plan validator, gen UI, web search, tools, workspace delete, etc. |

### Pending (documented, not built yet)

Roadmap specs live under [`docs/`](docs/). What's actually left:

| Area | Notes |
|------|--------|
| **Workspace derivation cache** | Packet is re-derived per run; add LRU/TTL cache (Phase 6 of [`docs/workspace_derived_prompts.md`](docs/workspace_derived_prompts.md)) |
| **Execution Phase D** | After approve, call `plan_layout` → `render_ui` directly in code (drop orchestrator LLM turn) ([`docs/agent_execution_model.md`](docs/agent_execution_model.md)) |
| **Execution extras** | Optional early handoff, parallel block assembly |
| **Emphasis / hero block** | `emphasis` plumbing exists; full hero-layout treatment is phase 2 of [`docs/visual_summary_planner_authority.md`](docs/visual_summary_planner_authority.md) |
| **Pipeline explorer** | Not started |

**Product promise today:** users can upload docs, chat with citations, run **workspace-aware** agents with live traces, approve notes, and generate a **Visual summary** — layout planned by the LLM, grounded and validated in code — from a substantive agent answer.

---

## Features (detail)

| Area | What you get |
|------|----------------|
| **Auth** | Register / login (JWT), bcrypt password hashes; dev panel for local testing |
| **Tenancy** | Workspaces + membership (owner/member); documents, chunks, conversations, agent runs, notes, usage all scoped by `workspace_id` |
| **Workspace management** | Create, rename, edit description/tags, delete; workspace selector in UI |
| **Documents** | Upload, list, delete; S3-compatible storage (R2/B2) or local files + Postgres metadata; status lifecycle (uploaded → queued → processing → ready/failed) |
| **Ingest pipeline** | PDF, DOCX, txt/md, RST, CSV/TSV, HTML/XML, JSON/JSONL, YAML/TOML, INI/CFG, CSS, JS/TS, PY, SH, LOG → parse → chunk → embed |
| **Background jobs** | Redis + **RQ** worker for heavy ingest (API stays responsive); configurable queue on/off |
| **RAG chat** | Hybrid retrieval (pgvector + full-text RRF) → LLM rerank → top-k chunks → LLM answer with **SSE streaming**; sources (filename, score, snippet) |
| **Chat ↔ Agent mode** | Same Chat page toggle: RAG by default, or tool-using agent + HITL |
| **Denial** | Off-topic / empty retrieval → no fake sources (configurable `rag_min_score`) |
| **Conversations** | Create, list, delete conversations; per-conversation message history with citations |
| **Agents (main)** | Tools: `get_current_date`, `list_documents`, `search_documents` (semantic), `web_search`, `create_note` (HITL) |
| **Visual Summary agent** | After HITL approve: handoff extract → `plan_layout` → validate/replan → `render_ui` → generative UI on the run |
| **Generative UI** | Structured visual blocks (summary, tables, progress, FAQ, chips, steps, …); normalization + grounding on API/web |
| **Agent streaming** | Live SSE traces (`llm_start`, `llm_end`, step, status, done events) |
| **HITL + resume** | Write tools and presentation offer pause for Approve / Reject; **Approve executes then resumes** the agent loop with SSE |
| **Notes** | Full CRUD for notes (list, get, create via agent, update, delete); editor with sidebar |
| **Usage tracking** | Token usage events (prompt/completion/total per kind); aggregated **Usage** page with by-kind breakdown |
| **Rate limits** | Per-user fixed-window limits on chat (20/min), ingest (10/min), agent starts (10/min); Redis backed with in-memory fallback |
| **Settings** | Profile (email update), change password, workspace management (incl. description & tags) |
| **Dashboard** | Home page with workspace stats, quick actions, recent activity |
| **Theme** | Light/dark mode toggle with persistent preference |
| **UI components** | Toast notifications, confirm dialogs, error boundary, empty states, skeletons, badges, cards, alerts, sheets |
| **Accessibility** | Skip-to-content link, semantic HTML, keyboard-navigable, focus management |
| **Structured logging** | Request ID correlation (`X-Request-ID`), JSON structured logs, per-request timing |
| **Dev tools** | `DEV_MODE` panel to list users, set/reset test passwords; Swagger docs at `/docs` |

---

## Architecture

```text
┌──────────────┐     JWT      ┌─────────────────┐
│  React Web   │─────────────▶│  FastAPI (API)  │
│  Vite :5173  │   SSE stream └────────┬────────┘
└──────────────┘  (chat+agent)         │
                                        ├──── Postgres (users, docs, chunks, conversations, messages, agents, notes, usage)
                                        │
                                        ├──── OpenAI (embeddings + chat; configurable via env)
                                        │
                                        └──── Redis
                                               │
                                               ├─ RQ queue: document ingest jobs
                                               └─ rate-limit counters
                                                      │
                                               ┌──────▼──────┐
                                               │ RQ Worker   │
                                               │ (ingest)    │
                                               └─────────────┘
```

```mermaid
flowchart LR
  Browser[React UI] --> API[FastAPI]
  API --> PG[(Postgres)]
  API --> Redis[(Redis)]
  API --> LLM[OpenAI API]
  Redis --> Worker[RQ Worker]
  Worker --> PG
  Worker --> LLM
```

### Agent run flow (shipped)

```text
User goal
    → Main agent tool loop (date → search/web; parallel reads)
    → final_answer
    → optional HITL: create_note
    → HITL: offer Visual Summary
         → approve → handoff extract → Visual Summary agent
              (plan_layout → validate/replan → render_ui)
         → presentation_spec on run
    → UI: Answer tab + Visual summary tab + Trace
```

Main agent and Visual Summary are **sequential phases of one `AgentRun`**, not two concurrent runs. See [`docs/agent_execution_model.md`](docs/agent_execution_model.md).

### Request paths (mental model)

| User action | What runs |
|-------------|-----------|
| Login / list docs / chat | **API only** |
| Ingest document | **API enqueues** → **Worker** embeds → Postgres |
| Agent run + visual summary | **API** (tools + optional approval; short visual loop) |

---

## Stack

| Layer | Choice |
|-------|--------|
| API | Python 3.12+, FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| Package mgmt | `uv` |
| Web | React, Vite, TypeScript, Tailwind-style tokens |
| DB | PostgreSQL 16 + **pgvector** (HNSW); Alembic migrations |
| Queue / cache | Redis 7 + RQ |
| File storage | S3-compatible (Cloudflare R2 / Backblaze B2) behind a storage interface; local fallback |
| Hosting | Vercel (web) · Render (API) · Upstash (Redis) |
| LLM | OpenAI-compatible (`text-embedding-3-small`, `gpt-4o-mini` by default) |
| Agents | Tool loop + HITL for writes and visual summary; presentation package for handoff/layout/render |

---

## Repo layout

```text
sourcebook/
├── apps/
│   ├── api/                         # FastAPI backend
│   │   ├── app/
│   │   │   ├── agents/              # profiles, runner, tools, gen_ui, visual tools, execution_trace
│   │   │   ├── chat/                # RAG + SSE streaming
│   │   │   ├── ingestion/           # parse, chunk, embed, retrieve
│   │   │   ├── presentation/        # handoff, layout, planner, plan validator, render engine
│   │   │   ├── middleware/          # request logging, request ID
│   │   │   ├── routers/             # auth, docs, chat, agents, notes, usage, workspaces, dev
│   │   │   ├── workers/             # RQ ingest jobs + queue
│   │   │   ├── config.py
│   │   │   ├── models.py
│   │   │   └── ...
│   │   ├── tests/                   # agent + presentation + ingest tests
│   │   ├── main.py
│   │   └── pyproject.toml
│   └── web/                         # React + Vite frontend
│       └── src/
│           ├── pages/               # Dashboard, Login, Documents, Chat, Agents, Notes, Usage, Settings
│           ├── components/          # layout, chat, agents (trace + GenerativeUI), theme, ui, workspace
│           ├── hooks/               # useAgentStream, queries, …
│           ├── api.ts               # API client + SSE streaming
│           └── App.tsx
├── docs/                            # Product plans (visual summary, workspace context, execution)
└── README.md
```

### Product docs

| Doc | Purpose |
|-----|---------|
| [`docs/visual_summary.md`](docs/visual_summary.md) | Visual Summary + workspace-centric agent vision; baseline vs planned |
| [`docs/visual_summary_ui_plan.md`](docs/visual_summary_ui_plan.md) | How Visual Summary should generate use-case UI (affordances, assembly) |
| [`docs/workspace_derived_prompts.md`](docs/workspace_derived_prompts.md) | WorkspaceContextPacket — no hardcoded verticals |
| [`docs/agent_execution_model.md`](docs/agent_execution_model.md) | Sequential vs parallel execution across main + visual agents |

---

## Prerequisites

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- Node.js 20+ (for web)
- **Postgres** (with `pgvector` if you use embeddings) and **Redis**, reachable from the API
- OpenAI API key (or other OpenAI-compatible endpoint)

---

## Quick start (local)

You typically need **four** things: **Postgres, Redis, API, Worker**, plus **Web**.

### 1. Infrastructure

Run Postgres and Redis yourself (local install, managed cloud, or any host). Point `DATABASE_URL` and `REDIS_URL` at them in `.env` — there is no project `docker-compose` stack.

### 2. API env

```bash
cd apps/api
cp ../../.env.example .env   # or create apps/api/.env
```

Minimum useful `.env`:

```env
DATABASE_URL=postgresql+psycopg://sourcebook:sourcebook@127.0.0.1:5432/sourcebook
REDIS_URL=redis://127.0.0.1:6379/0

OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini

INGEST_USE_QUEUE=true
DEV_MODE=true
```

> Use **`OPENAI_API_KEY`** (not `OPEN_API_KEY`).  
> After changing **embedding** model, **re-ingest** documents.

Install & start:

```bash
uv sync
uv run python main.py
```

- Health: http://127.0.0.1:8000/health  
- Swagger: http://127.0.0.1:8000/docs  

### 3. Ingest worker (required when queue is on)

**Separate terminal:**

```bash
cd apps/api
uv run python -m app.workers.rq_worker
```

You should see: `Listening on sourcebook-ingest...`

On **macOS**, the worker uses `SimpleWorker` (avoids RQ fork crashes).

If status stays **`queued`**, the worker is not running or not on the same `REDIS_URL`.

Sync fallback (no worker):

```env
INGEST_USE_QUEUE=false
```

### 4. Web

```bash
cd apps/web
npm install
npm run dev
```

Open the Vite URL (e.g. http://127.0.0.1:5173).

---

## App map (UI)

| Route | Purpose |
|-------|---------|
| `/` | **Dashboard** — workspace stats, quick actions, recent activity |
| `/login` | Auth; **DEV** panel can list users / set test passwords when `DEV_MODE=true` |
| `/documents` | Upload, ingest (queue), status badges |
| `/chat` | Streaming RAG chat + citations; **Agent** mode toggle for tools + HITL |
| `/agents` | Agent runs, Answer / Visual summary / Trace, approve presentation or writes |
| `/notes` | Notes list, sidebar, editor |
| `/usage` | Logged token usage summary + per-event breakdown |
| `/settings` | Profile, password, workspaces (name, description, tags) |

---

## Document status lifecycle

```text
uploaded → queued → processing → ready
                              ↘ failed  (error message stored)
```

Only **ready** docs contribute useful RAG chunks (after successful embed).

---

## Agent HITL flows

### Write tool (`create_note`)

```text
Goal → tools (list/search/web) → if create_note → waiting_approval
     → Approve → execute write → resume LLM loop → final answer / next steps
     → Reject  → cancelled
```

### Visual Summary (presentation)

```text
Main agent final_answer (substantive)
     → offer presentation (waiting_approval)
     → Approve → handoff extract → plan_layout → render_ui
               → presentation_spec → Visual summary tab
     → Reject  → keep text-only answer
```

---

## Rate limits (defaults)

Per user, per 60s window (Redis; in-memory fallback if Redis down):

| Scope | Default |
|-------|---------|
| Chat | 20 / min |
| Ingest | 10 / min |
| Agent starts | 10 / min |

Tune via `RATE_LIMIT_*` env vars; set `RATE_LIMIT_ENABLED=false` for heavy local testing.

---

## Roadmap status (honest)

| Area | Status |
|------|--------|
| Core product (auth, workspaces, docs, ingest, RAG chat) | **Done** |
| Background ingest + rate limits + usage | **Done** |
| Main agent tools + HITL + SSE traces | **Done** |
| Visual Summary Phase A + B (handoff, plan, validate, render) | **Done** |
| Generative UI blocks + web normalize/render | **Done** |
| Workspace-derived prompts / packet | **Done** — packet + injection + Settings preview ([`docs/workspace_derived_prompts.md`](docs/workspace_derived_prompts.md)) |
| Use-case UI assembly (code-first, no vertical hardcoding) | **Done** — UiIntent assembly + planner-LLM authority ([`docs/visual_summary_ui_plan.md`](docs/visual_summary_ui_plan.md)) |
| Hybrid retrieval (pgvector + full-text RRF) + LLM rerank | **Done** |
| Deployed live demo | **Done** — Vercel (web) + Render (API) + Upstash (Redis) |
| Workspace derivation cache | **Planned** |
| Execution Phase D (code-direct visual pipeline) | **Planned** |
| Pipeline explorer | **Not done** |

Canonical product vision and pipeline detail: [`docs/visual_summary.md`](docs/visual_summary.md).

---

## API surface (main)

```text
POST   /auth/register | /auth/login
GET    /workspaces
POST   /workspaces                    create workspace
PATCH  /workspaces/{id}               update name/description/tags (owner)
DELETE /workspaces/{id}               delete (owner only)
GET    /me
PUT    /me                            update profile email
PUT    /me/password                   change password
POST   /documents                     multipart upload
GET    /documents?workspace_id=
DELETE /documents/{id}
POST   /documents/{id}/ingest         enqueue or sync
POST   /conversations
GET    /conversations?workspace_id=
DELETE /conversations/{id}
GET    /conversations/{id}/messages
POST   /chat | /chat/stream           SSE streaming
POST   /chat/suggestions
POST   /agents/runs
POST   /agents/runs/stream            SSE agent trace
POST   /agents/runs/{id}/approve
POST   /agents/runs/{id}/approve/stream  SSE resume / visual summary trace
GET    /agents/runs?workspace_id=
GET    /agents/runs/{id}
DELETE /agents/runs/{id}
GET    /notes?workspace_id=
GET    /notes/{id}
PUT    /notes/{id}
DELETE /notes/{id}
GET    /usage/summary
GET    /usage/events
GET    /usage/events/{id}
GET    /health | /health/db
```

Dev-only (when `DEV_MODE=true`): `GET /dev/users`, `POST /dev/users/set-password`, `POST /dev/users/set-all-passwords`.

---

## Security notes

Summary:

- Passwords are **hashed** (never stored or displayed as originals).  
- `DEV_MODE` test-user panel is **local only** — set `DEV_MODE=false` outside personal machines.  
- Multi-tenant queries filter by workspace membership; retrieval always filters by `workspace_id`.  
- Agent tools are **allowlisted**; **write** tools (`create_note`) and **presentation** require human approval.  
- Per-user **rate limits** on chat, ingest, and agent starts.  
- **Structured logs** (JSON) with `X-Request-ID` correlation.  
- Do not commit `.env` or API keys.

---

## Interview talking points

1. Multi-tenant RAG: isolate vectors/docs by workspace.  
2. Streaming UX for chat + agent traces (SSE).  
3. Async ingest (queue + worker) vs blocking API.  
4. Agent tools with max steps, parallel read batching, and HITL for writes (approve → resume).  
5. Two-phase agent product path: research answer → Visual Summary generative UI (handoff → plan → render).  
6. Rate limits (Redis + in-memory fallback) and usage logging for cost control.  
7. Structured logging with request ID correlation.  
8. Full-stack: FastAPI + React/Vite + Postgres + Redis, env-driven config.

---

## License

Optional — add a license if you open-source publicly.

---

*Sourcebook · FastAPI + React · build week by week, demo by slice.*
