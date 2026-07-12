# Sourcebook

Multi-tenant **document AI workspace**: upload files, run an ingest pipeline (parse → chunk → embed), **chat with grounded answers and citations**, and run **tool-using agents** with human approval for writes.

> Not a toy chatbot — a small AI product with real backend concerns: tenancy, async jobs, rate limits, traces, and evals.

---

## Features

| Area | What you get |
|------|----------------|
| **Auth** | Register / login (JWT), bcrypt password hashes |
| **Tenancy** | Workspaces + membership; documents and vectors scoped by `workspace_id` |
| **Documents** | Upload, list, delete; local file storage + Postgres metadata |
| **Ingest** | txt/md parse → chunk → embed; status `queued` → `processing` → `ready` / `failed` |
| **Background jobs** | Redis + **RQ** worker for heavy ingest (API stays responsive) |
| **RAG chat** | Retrieve top chunks → LLM answer; **SSE streaming**; sources (filename, score, snippet) |
| **Chat ↔ Agent mode** | Same Chat page toggle: RAG by default, or tool-using agent + HITL |
| **Denial** | Off-topic / empty retrieval → no fake sources |
| **Agents** | Tools: `list_documents`, `search_documents`, `create_note`; step timeline (+ dedicated Agents page) |
| **HITL** | `create_note` pauses at `waiting_approval` until Approve / Reject |
| **Usage** | Token usage events + **Usage** page |
| **Rate limits** | Per-user limits on chat, ingest, agent starts |
| **Evals** | Manual golden set: [`evals/sourcebook-v1.md`](evals/sourcebook-v1.md) (**10/12** on design-doc Qs) |

---

## Architecture

```text
┌──────────────┐     JWT      ┌─────────────────┐
│  React Web   │─────────────▶│  FastAPI (API)  │
│  Vite :5173  │              └────────┬────────┘
└──────────────┘                       │
                                       ├──── Postgres (users, docs, chunks, chat, agents, usage)
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

### Request paths (mental model)

| User action | What runs |
|-------------|-----------|
| Login / list docs / chat | **API only** |
| Ingest document | **API enqueues** → **Worker** embeds → Postgres |
| Agent run | **API** (tools + optional approval) |

---

## Stack

| Layer | Choice |
|-------|--------|
| API | Python 3.12+, FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| Package mgmt | `uv` |
| Web | React, Vite, TypeScript, Tailwind-style tokens |
| DB | PostgreSQL 16 |
| Queue / cache | Redis 7 + RQ |
| LLM | OpenAI-compatible (`text-embedding-3-small`, `gpt-4o-mini` by default) |
| Agents | Tool loop + LangGraph-related deps; HITL for writes |

---

## Repo layout

```text
sourcebook/
├── apps/
│   ├── api/                 # FastAPI
│   │   ├── app/
│   │   │   ├── agents/      # tools + runner
│   │   │   ├── chat/        # RAG + SSE
│   │   │   ├── ingestion/   # parse, chunk, embed, retrieve
│   │   │   ├── routers/     # HTTP routes
│   │   │   └── workers/     # RQ ingest jobs
│   │   ├── main.py
│   │   └── pyproject.toml
│   └── web/                 # React UI
├── docs/                    # Roadmap & career plan
├── evals/                   # RAG golden-set notes
├── docker-compose.yml       # Postgres + Redis
└── README.md
```

---

## Prerequisites

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- Node.js 20+ (for web)
- Docker (Postgres + Redis) **or** equivalent services reachable on your network
- OpenAI API key (or other OpenAI-compatible endpoint)

---

## Quick start (local)

You typically need **four** things: **Postgres, Redis, API, Worker**, plus **Web**.

### 1. Infrastructure

```bash
cd /path/to/sourcebook
docker compose up -d postgres redis
```

If Postgres/Redis run on another machine (e.g. Windows Docker), point env URLs at that host IP.

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

Install & create tables (on first run, models use `create_all` where needed; or start API and use existing DB):

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
| `/login` | Auth; **DEV** panel can list users / set `password123` when `DEV_MODE=true` |
| `/documents` | Upload, ingest (queue), status badges |
| `/chat` | Streaming RAG chat + sources; **Agent** mode for tools + HITL |
| `/agents` | Agent run history, step timeline, approve/reject writes, notes list |
| `/usage` | Logged token usage for your user |

---

## Document status lifecycle

```text
uploaded → queued → processing → ready
                              ↘ failed  (error message stored)
```

Only **ready** docs contribute useful RAG chunks (after successful embed).

---

## Agent HITL flow

```text
Goal → tools (list/search) → if create_note → waiting_approval
     → user Approves → note created → completed
     → user Rejects  → cancelled
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

## Evals

Manual golden set and results:

- [`evals/sourcebook-v1.md`](evals/sourcebook-v1.md)  
- Latest recorded score: **10/12 (83%)** on a Vercel design-system markdown doc (after retest of ambiguous Qs).  
- Includes denial cases (off-topic should not invent sources).

---

## Roadmap status (honest)

See [`docs/GREENFIELD_APP_ROADMAP.md`](docs/GREENFIELD_APP_ROADMAP.md).

| Area | Status |
|------|--------|
| Weeks 0–4 core product | Largely **done** |
| Background ingest + rate limits | **Done** |
| **Deployed live demo** | **Not done** |
| Hybrid retrieval / pipeline explorer | Not done (Week 6+) |
| Demo video / job apply pack | Not done (Week 7–8) |

Plans / career strategy: [`docs/CAREER_SWITCH_30_DAY_PLAN.md`](docs/CAREER_SWITCH_30_DAY_PLAN.md).

---

## API surface (main)

```text
POST   /auth/register | /auth/login
GET    /workspaces
GET    /me
POST   /documents                 multipart upload
GET    /documents?workspace_id=
DELETE /documents/{id}
POST   /documents/{id}/ingest     enqueue or sync
POST   /conversations
GET    /conversations?workspace_id=
POST   /chat | /chat/stream
POST   /agents/runs
POST   /agents/runs/{id}/approve
GET    /agents/runs?workspace_id=
GET    /notes?workspace_id=
GET    /usage/summary
GET    /health
```

Dev-only (when `DEV_MODE=true`): `/dev/users`, set test passwords.

---

## Security notes

Summary:

- Passwords are **hashed** (never stored or displayed as originals).  
- `DEV_MODE` test-user panel is **local only** — set `DEV_MODE=false` outside personal machines.  
- Multi-tenant queries filter by workspace membership; retrieval always filters by `workspace_id`.  
- Agent tools are **allowlisted**; **write** tools (`create_note`) require human approval.  
- Per-user **rate limits** on chat, ingest, and agent starts.  
- **Structured logs** (JSON) with `X-Request-ID` correlation.  
- Do not commit `.env` or API keys.

Full write-up (prompt injection, allowlist, production checklist):

→ **[docs/SECURITY.md](docs/SECURITY.md)**

---

## Interview talking points

1. Multi-tenant RAG: isolate vectors/docs by workspace.  
2. Streaming UX + citations + denial path.  
3. Async ingest (queue + worker) vs blocking API.  
4. Agent tools with max steps and HITL for writes.  
5. Rate limits and usage logging for cost control.  
6. Eval golden set, not vibes-only quality.

---

## License

Optional — add a license if you open-source publicly.

---

*Sourcebook · FastAPI + React · build week by week, demo by slice.*
