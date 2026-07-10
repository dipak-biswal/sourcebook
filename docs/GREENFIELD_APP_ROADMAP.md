# Sourcebook — Greenfield App Roadmap

> **Product:** **Sourcebook**  
> **Repo / folder name:** `sourcebook`  
> **Intent:** New git repo. Build **week by week**. Each feature teaches **implementation + system design**.  
> **Stack lock:** Python **FastAPI** backend · **React** frontend · Postgres · Redis · vector store · LLM APIs · LangGraph  
> **For future sessions:** Read this + `CAREER_SWITCH_30_DAY_PLAN.md`. Coach **one feature slice at a time**.  
> **Plans live in:** `agent-docs` folder on Desktop (strategy docs only). **Code ships in:** `sourcebook` repo.

---

## 1. Product name & branding (locked)

| Item | Value |
|------|--------|
| **Product name** | **Sourcebook** |
| **Repo / folder** | `sourcebook` |
| **GitHub (suggested)** | `github.com/<you>/sourcebook` |
| **UI title** | Sourcebook |
| **Package / project slug** | `sourcebook` |

**One-liner:**

> **Sourcebook** — multi-tenant document workspace: upload files, chat with grounded answers (RAG) and **citations**, run **tool-using agents**, inspect pipeline quality.

**Not a toy chatbot.** It is a small **AI product** with real backend concerns.

**Do not use these names for the new product:** AgentDocs, DocAgent, DocuForge, LedgerAI, agent-docs.

---

## 2. Who it’s for (keeps scope honest)

| Persona | Need |
|---------|------|
| Individual user | Upload docs, ask questions, get citations |
| Power user | Tune retrieval, see agent steps, approve actions |
| Interviewer | Clear architecture, multi-tenant safety, failure modes |

---

## 3. Feature map (what to build)

### Tier A — Must ship (job + system design core)

| # | Feature | Why (skill + system design) |
|---|---------|------------------------------|
| A1 | **Auth + multi-tenant workspaces** | AuthN/AuthZ, data isolation |
| A2 | **Document upload & storage** | File I/O, object/local storage, metadata DB |
| A3 | **Ingest pipeline** (parse → chunk → embed → index) | Async jobs, pipeline stages, idempotency |
| A4 | **RAG chat with streaming + citations** | SSE, context windows, grounded gen |
| A5 | **Conversation history** | Redis/Postgres session design |
| A6 | **Agent with tools** (search docs, create note/ticket) | Tool calling, loops, limits |
| A7 | **Human-in-the-loop approval** | Safety, workflow design |
| A8 | **Basic observability** | Logs, run traces, token usage |
| A9 | **Eval harness (minimal)** | Quality loops, not vibes |
| A10 | **Deployed demo** | Real env, secrets, CORS, health checks |

### Tier B — Strong differentiators (add after A works)

| # | Feature | System design angle |
|---|---------|---------------------|
| B1 | **Retrieval strategy switcher** (vector / BM25 / hybrid) | Tradeoffs, ranking |
| B2 | **Pipeline explorer UI** (chunks, embeddings preview) | Debuggability, DX |
| B3 | **Background workers** (Celery/RQ/arq) for ingest | Queues, retries, dead letters |
| B4 | **Rate limiting + usage quotas** | Abuse, cost control |
| B5 | **Prompt injection defenses** | Security design |
| B6 | **Webhooks / outbound tool** (e.g. Slack stub) | Integration patterns |
| B7 | **Share workspace / invite** (simple) | RBAC basics |
| B8 | **Feedback thumbs up/down on answers** | Closed-loop product quality |

### Tier C — Stretch only (if ahead or post-offer)

| # | Feature | Notes |
|---|---------|--------|
| C1 | Knowledge graph | Nice; easy to over-scope |
| C2 | Multi-agent supervisor | Only after single agent solid |
| C3 | Fine-tuning | Not needed for AI App Engineer |
| C4 | Multi-region / K8s | Overkill for portfolio |
| C5 | PDF complex layout / OCR | Time sink |
| C6 | Real-time collab editing | Not core to AI eng story |
| C7 | Mobile app | Skip |
| C8 | Billing/Stripe | Only if extra week |

**Rule:** Do **not** start Tier C until Tier A is demoable.

---

## 4. System design scenarios each feature covers

Use these as interview talking points while you build.

| Feature | Design prompt you can answer |
|---------|------------------------------|
| Auth + tenants | “Design multi-tenant SaaS data isolation” |
| Upload + ingest | “Design a document processing pipeline” |
| Queue workers | “How do you handle 10k uploads/hour?” |
| Vector index | “Design semantic search for private docs” |
| RAG chat | “Design ChatGPT over company knowledge” |
| Streaming | “How do you stream LLM tokens to browsers?” |
| History store | “Where do you put session state and why?” |
| Agent + tools | “Design an agent that can take actions safely” |
| HITL | “How do you prevent destructive agent actions?” |
| Rate limits / cost | “How do you stop one user from burning $10k API?” |
| Evals | “How do you know RAG quality improved?” |
| Observability | “Debug a wrong answer in production” |
| Hybrid retrieval | “Vector vs keyword — when each wins” |

---

## 5. Week-by-week build plan (greenfield)

Assume **new folder + git init**. ~48 hrs/week. React FE + FastAPI BE.

### Week 0 — Skeleton (1–2 days)

**Build:**
- [ ] Repo root named **`sourcebook`**
- [ ] Monorepo or two folders: `apps/api`, `apps/web`
- [ ] FastAPI hello + `/health` (app title Sourcebook in OpenAPI)
- [ ] React app shell (layout, router, **Sourcebook** in header)
- [ ] Docker Compose: **Postgres + Redis**
- [ ] `.env.example`, **README.md** titled Sourcebook
- [ ] First commit: `chore: sourcebook week 0 skeleton`

**System design note:** boundaries (browser → API → DB), 12-factor config.

---

### Week 1 — Platform core (A1, A2 partial)

**Build:**
- [ ] User auth (JWT or Clerk/Auth.js-style; pick one)
- [ ] `Workspace` + membership (even if 1 user = 1 workspace)
- [ ] CRUD: documents metadata in Postgres
- [ ] File upload to **local disk or S3-compatible** (MinIO optional)
- [ ] List/delete documents (tenant-scoped queries)
- [ ] React: login + documents list + upload

**SD coverage:** multi-tenancy, authn vs authz, file storage vs DB metadata.

**Demo:** User A cannot see User B’s files.

---

### Week 2 — Ingest + chat foundation (A3 partial, A5)

**Build:**
- [ ] Parse txt/md (PDF later if time)
- [ ] Chunker (size + overlap config)
- [ ] Embeddings → vector store (pgvector **or** Chroma — pick one)
- [ ] Sync ingest first (async in week 3–4 if needed)
- [ ] Conversations + messages tables
- [ ] Non-streaming chat endpoint (then stream)
- [ ] React chat page (basic)

**SD coverage:** pipeline stages, embedding index, conversation data model.

**Demo:** Upload file → ask question → answer (even without perfect citations yet).

---

### Week 3 — Production RAG (A4, A8 partial, A9 start)

**Build:**
- [ ] Streaming SSE from FastAPI → React
- [ ] Citations (chunk id, filename, snippet, score)
- [ ] “I don’t know” when retrieval empty
- [ ] Tenant filter on **every** vector query
- [ ] Token usage log table
- [ ] 10–15 question eval markdown + script or manual sheet
- [ ] React: sources chips, loading, errors

**SD coverage:** “Design RAG chat”, failure modes, cost tracking.

**Demo:** Grounded answer + sources + denial path.

---

### Week 4 — Agents (A6, A7, A8)

**Build:**
- [ ] LangGraph (or equivalent) agent loop
- [ ] Tools: `search_documents`, `list_documents`, `create_task`/`create_note`
- [ ] `max_steps`, tool error feedback
- [ ] Persist `AgentRun` + `AgentStep` (trace UI)
- [ ] Approval gate for write tools
- [ ] React: show tool calls live / step timeline

**SD coverage:** agent safety, orchestration, audit log.

**Demo:** “Create a task from this doc” → approve → task exists.

---

### Week 5 — Hardening + Tier B starters (B3, B4, B5, deploy A10)

**Build:**
- [ ] Move heavy ingest to **background worker** (queue)
- [ ] Retries + failed job status on document
- [ ] Rate limit chat/ingest per user
- [ ] Basic prompt-injection notes + tool allowlist
- [ ] Health checks, structured logs
- [ ] Deploy API + web + DB (Railway/Render/Fly + Vercel)
- [ ] README architecture diagrams

**SD coverage:** queues, backpressure, security, deploy topology.

**Demo:** Live URL for interviews.

---

### Week 6 — Differentiators (pick 2–3 from Tier B)

**Recommended pick:**
- [ ] B1 Hybrid retrieval toggle  
- [ ] B2 Pipeline explorer (chunk list + retrieve preview)  
- [ ] B8 Answer feedback  

**Optional:** B6 webhook stub, B7 invite if easy.

**SD coverage:** ranking quality, observability UX, product loop.

---

### Week 7–8 — Interview pack + polish

**Build/fix:**
- [ ] Demo video 3 min  
- [ ] Eval results in README  
- [ ] One load-test note (even k6/curl script light)  
- [ ] Fix bugs from self-dogfooding  
- [ ] Apply to jobs daily  

**SD drills (speak, don’t overbuild):**
1. Design multi-tenant RAG SaaS  
2. Design safe agents with tools  
3. Scale ingest 100×  
4. Cost explosion mitigation  

---

## 6. Suggested data model (keep it simple)

```
User
Workspace
WorkspaceMember (user_id, workspace_id, role)
Document (workspace_id, filename, status, storage_key, error)
Chunk (document_id, content, metadata, embedding ref)
Conversation (workspace_id, user_id, title)
Message (conversation_id, role, content, citations JSON)
AgentRun (workspace_id, goal, status, token_usage)
AgentStep (run_id, type, tool_name, input, output)
UsageEvent (user_id, kind, tokens, cost_estimate)
Task/Note (workspace_id, title, body)  # agent write target
```

---

## 7. API surface (minimum)

```
POST   /auth/register|login   (or external auth)
GET    /workspaces
POST   /documents             multipart upload
GET    /documents
DELETE /documents/{id}
POST   /documents/{id}/reindex
GET    /conversations
POST   /conversations
POST   /chat                  SSE stream
POST   /agents/runs           start agent
POST   /agents/runs/{id}/approve
GET    /agents/runs/{id}
GET    /health
```

---

## 8. UI pages (minimum)

| Route | Purpose |
|-------|---------|
| `/login` | Auth |
| `/documents` | Upload, list, status (queued/ready/failed) |
| `/chat` | Streaming RAG chat + citations |
| `/agents` or panel in chat | Runs, steps, approve button |
| `/settings` | API usage summary (simple) |
| Optional `/pipeline/:docId` | Chunk/retrieve explorer (Week 6) |

---

## 9. Feature ideas backlog (if you want more later)

Only after Tier A+B. Pick based on job target.

**Product**
- Folders/tags for documents  
- Cross-doc compare agent  
- Scheduled re-index  
- Export answer to Markdown/PDF  
- Templates (“summarize risks”, “extract action items”)  
- Multi-file chat scope picker  

**AI quality**
- Reranker stage  
- Query rewriting  
- HyDE  
- Citation click → highlight chunk  
- Hallucination self-check node  

**Platform**
- Admin usage dashboard  
- Audit log export  
- Feature flags  
- OpenAPI-generated client  

**Integrations**
- GitHub repo ingest  
- Notion/Google Drive stub  
- Slack bot entrypoint  

---

## 10. What to drop from old agent-docs (on purpose)

**Sourcebook** rebuilds **cleaner** — reuse ideas only, not every experiment from the old AgentDocs codebase.

| Bring (concept) | Leave for later / drop |
|-----------------|-------------------------|
| RAG + stream chat | 10 retrievers on day 1 |
| LangGraph agent | Full knowledge graph |
| Citations | Complex gen-UI flashcards first |
| Documents UI | Neo4j dependency on day 1 |
| Redis sessions | Every advanced node |

**Start narrow → deepen.** Complexity is earned after the happy path works.

---

## 11. Definition of done (portfolio)

**Sourcebook** is job-ready when:

1. Live demo URL (or reliable local + video) labeled **Sourcebook**  
2. Multi-tenant isolation proven  
3. RAG + citations + denial  
4. Agent + tool + approval + trace  
5. Queue or clear story for async ingest  
6. README titled **Sourcebook** with architecture + runbook + eval notes  
7. Public repo **`sourcebook`**  
8. You can design “chat with company docs” on a whiteboard in 10 minutes  

---

## 12. New repo bootstrap (when you start)

```bash
mkdir -p ~/projects/sourcebook && cd ~/projects/sourcebook
git init
mkdir -p apps/api apps/web docs
# then Week 0 skeleton under coach guidance
```

**First session prompt:**

```text
Read GREENFIELD_APP_ROADMAP.md and CAREER_SWITCH_30_DAY_PLAN.md.
Product name: Sourcebook.
I created a new empty repo at <path>/sourcebook.
Start Week 0 skeleton — one step at a time.
```

---

## 13. Priority cheat sheet

```
Must:     Auth/tenant → Upload → Ingest → RAG stream+cite → History
Must:     Agent tools → HITL → Traces → Deploy
Should:   Queue ingest → Rate limits → Hybrid retrieve → Pipeline UI
Could:    Feedback → Webhooks → Invites
Won't:    KG, multi-agent circus, K8s, billing (until later)
```

---

*Product: **Sourcebook** · Repo: **sourcebook**. Build features in order. Each week ends with a demoable slice. System design is the “why” you write in README and practice out loud — not a separate course.*
