# Build Guide — Step by Step

> **STATUS:** Secondary / reference for studying the **agent-docs** codebase.  
> **Portfolio product to ship:** **Sourcebook** (`sourcebook` repo).  
> **Primary build playbook:** **`GREENFIELD_APP_ROADMAP.md`**.  
> **Strategy:** **`CAREER_SWITCH_30_DAY_PLAN.md`**.  
>  
> Use **this file only** if the user wants to learn by running/exploring **agent-docs**.  
> For the career switch build, coach from **GREENFIELD_APP_ROADMAP.md** one step at a time.

---

## 0. Rules for the AI coach (mandatory)

1. Default portfolio = **Sourcebook** → follow **GREENFIELD_APP_ROADMAP.md** + **CAREER_SWITCH_30_DAY_PLAN.md**.  
2. Use **this BUILD_GUIDE** only when user is working inside **agent-docs** for reference learning.  
3. Ask: **“Which step ID are you on?”** (e.g. `W1-S3`). If unknown and on agent-docs, start at `W0-S1`.  
4. Give **only the current step**: goal → commands/files → **Done when**.  
5. Wait for the user to finish (or paste errors) before the next step.  
6. **Backend lock:** Python / FastAPI. Frontend: React. Do not switch to Next-as-backend.  
7. Keep language **clear and short**. No LinkedIn drafts unless asked.  
8. Prefer **working demo** over perfect theory.

---

## 1. Decision locks

| Item | Value |
|------|--------|
| **Portfolio product** | **Sourcebook** (repo: `sourcebook`) — greenfield |
| **This file’s target** | **agent-docs** monorepo (reference only) |
| Backend | **Python + FastAPI** |
| Frontend | **React** |
| Goal | Job in ~**8 weeks**, ~**48 hrs/week** |

### What “building” means for Sourcebook

→ See **GREENFIELD_APP_ROADMAP.md** (Week 0–8 features).

### What this file means (agent-docs reference)

1. **Run** the full stack in `agent-docs`  
2. **Map** skills to folders  
3. **Own** paths by reading/fixing  
4. Do **not** replace Sourcebook as the main portfolio unless user says so  

| Interview skill | agent-docs reference folders |
|-----------------|------------------------------|
| FastAPI / API | `apps/api/main.py`, `chat/`, `ingestion/` |
| Chat + streaming | `apps/api/chat/`, `apps/web/app/chat/` |
| RAG | `apps/api/ingestion/`, retrieval, embeddings |
| Agents | `apps/api/agents/` especially `graph.py` |
| React UI | `apps/web` |

---

## 2. How a session should look

```
User: continue / start / I'm on W1-S2
AI:
  1. Confirms step ID
  2. Goal (1 sentence)
  3. Exact actions (commands + files)
  4. Done when (checklist)
  5. "Reply DONE or paste error"
```

**Step ID format:** `W{week}-S{step}`  
Example: `W0-S1`, `W1-S3`, `W3-S2`

---

## 3. Repo map (memorize)

```
agent-docs/                   # REFERENCE monorepo (not Sourcebook)
├── apps/api/                 # Python FastAPI
│   ├── main.py
│   ├── chat/
│   ├── agents/graph.py
│   ├── ingestion/
│   └── config/
├── apps/web/                 # React/Next UI
├── docker-compose.yml
├── CAREER_SWITCH_30_DAY_PLAN.md   # strategy
├── GREENFIELD_APP_ROADMAP.md      # Sourcebook build (PRIMARY)
└── BUILD_GUIDE.md                 # THIS FILE (agent-docs study)
```

**Sourcebook greenfield layout (new repo):**

```
sourcebook/
├── apps/api/          # FastAPI
├── apps/web/          # React
├── docs/
├── docker-compose.yml
└── README.md
```

---

# PHASE W0 — Environment (do this first)

Complete **all W0 steps** before Week 1 deep work.

### W0-S1 — Open project and confirm git state
- [ ] Done  

**Goal:** You are in the right folder.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs
pwd
git status
```

**Done when:** path is `agent-docs` and git responds.

---

### W0-S2 — Install JS workspace
- [ ] Done  

**Goal:** Web app dependencies installed.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs
npm install
```

**Done when:** `npm install` finishes without fatal errors.

---

### W0-S3 — Install Python API deps
- [ ] Done  

**Goal:** API can import and run.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs/apps/api
# Prefer uv if used in this project:
uv sync
# OR follow apps/api/README / pyproject.toml install method if different
```

**Done when:** `uv run python -c "import fastapi; print('ok')"` works (or equivalent).

---

### W0-S4 — Start Redis (required for chat sessions)
- [ ] Done  

**Goal:** Redis up for sessions.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs
docker compose up -d redis
docker compose ps
```

**Done when:** Redis container is running on port `6379`.

---

### W0-S5 — Env files (API + web)
- [ ] Done  

**Goal:** Config exists; **no secrets committed**.  

**Actions:**
1. Find example env files (`.env.example`, README, `config/settings.py`).  
2. Create local `.env` / `.env.local` as required.  
3. Set LLM base URL (LM Studio default `http://localhost:1234` or cloud API keys).  
4. Confirm `.env` is gitignored.

**Done when:** settings load; user knows where API key / base URL goes.

---

### W0-S6 — Run API
- [ ] Done  

**Goal:** FastAPI listening.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs
npm run dev:api
# opens roughly http://127.0.0.1:8000
```

**Check:** open `http://127.0.0.1:8000/docs` (Swagger).  

**Done when:** `/docs` loads.

---

### W0-S7 — Run web
- [ ] Done  

**Goal:** UI loads and can talk to API.  

**Actions:**
```bash
cd /Users/dipakbiswal/Desktop/agent-docs
npm run dev:web
```

**Done when:** browser opens app (chat/documents routes reachable).

---

### W0-S8 — Smoke test product
- [ ] Done  

**Goal:** Prove the product works end-to-end once.  

**Actions:**
1. Start LLM endpoint if local (LM Studio) **or** configure cloud keys.  
2. Upload a small `.txt` or `.md` on Documents or chat attach.  
3. Ask a question about that file in Chat.  
4. Confirm stream + (if available) sources or polite denial.

**Done when:** You have seen either a grounded answer or a clear denial — not a crash.

---

### W0-S9 — Write “Runbook” notes (personal)
- [ ] Done  

**Goal:** You can restart the stack without help.  

**Write 5–10 lines in a private note:**
- Commands to start Redis, API, web, LLM  
- Ports  
- Where env vars live  

**Done when:** you can restart cold in <10 minutes.

---

# PHASE W1 — Own the backend (FastAPI)

**Theme:** You can explain and change the API like a senior IC.

### W1-S1 — Read `main.py` and list routes
- [ ] Done  

**Goal:** Know every top-level router.  

**Actions:**
1. Open `apps/api/main.py`.  
2. List routers (chat, ingestion, …).  
3. Open Swagger `/docs` and click 3 endpoints.

**Done when:** you can name the main route groups from memory.

---

### W1-S2 — Trace one request: health or list docs
- [ ] Done  

**Goal:** Follow request → handler → response.  

**Actions:**
1. Pick a simple GET from Swagger.  
2. Find the handler file.  
3. Note status codes and response shape.

**Done when:** you explain that path in 60 seconds.

---

### W1-S3 — Chat models & validation (Pydantic)
- [ ] Done  

**Goal:** See how inputs are validated.  

**Actions:**
1. Open `apps/api/chat/models.py` (and serializers if any).  
2. Compare fields to what the web sends.  
3. Change nothing yet — write what each field means.

**Done when:** short notes: request body fields for chat.

---

### W1-S4 — Chat service layer
- [ ] Done  

**Goal:** Know where business logic lives.  

**Actions:**
1. Open `apps/api/chat/service.py`.  
2. Find streaming function.  
3. Note: history load → agent/graph → yield chunks.

**Done when:** you can sketch that flow on paper.

---

### W1-S5 — Redis session storage
- [ ] Done  

**Goal:** Understand why Redis exists.  

**Actions:**
1. Open `apps/api/chat/storage/`.  
2. Answer: How is a session keyed? What is stored?

**Done when:** one-paragraph answer in your notes.

---

### W1-S6 — Small backend improvement (you build)
- [ ] Done  

**Goal:** Ship one intentional change.  

**Pick ONE (coach helps implement):**
- Better error JSON on one failure path  
- Clearer log line on chat start/end  
- Validate an edge case (empty message)  
- Tiny `/health` enrichment (version/env name) if missing  

**Done when:** change works + you can explain why.

---

### W1-S7 — Week 1 interview drill
- [ ] Done  

**Speak aloud (record optional):**
> “When a user sends a chat message, the request hits FastAPI, loads history from Redis, runs the agent graph, and streams tokens back over SSE to React.”

**Done when:** smooth 2-minute version without reading code.

---

# PHASE W2 — Own chat + streaming

### W2-S1 — Backend stream contract
- [ ] Done  

**Actions:** Read how SSE/chunks are yielded in `chat/service.py`.  
**Done when:** you know event/payload shape the UI expects.

---

### W2-S2 — Frontend stream consumer
- [ ] Done  

**Actions:** Open `apps/web/app/chat/` — find fetch/stream handling.  
**Done when:** you know where tokens append to message state.

---

### W2-S3 — Citations / UI states
- [ ] Done  

**Actions:** Trace how sources/denial render in UI.  
**Done when:** you can demo: answer with sources **or** denial.

---

### W2-S4 — Build: improve UX one notch
- [ ] Done  

**Pick ONE:**
- Clearer loading / stop generation  
- Better empty state  
- Error toast if API down  

**Done when:** merged/working locally.

---

### W2-S5 — Drill
- [ ] Done  

Explain: **Why stream?** (latency UX, cancel, progressive render)

---

# PHASE W3 — Own RAG pipeline

### W3-S1 — Ingestion entry
- [ ] Done  

**Actions:** Read `apps/api/ingestion/` — upload → pipeline entry.  
**Done when:** list stages in order.

---

### W3-S2 — Chunking
- [ ] Done  

**Actions:** Read chunking module; change a parameter in UI or config and observe chunk count.  
**Done when:** explain size/overlap tradeoff.

---

### W3-S3 — Embeddings + store
- [ ] Done  

**Actions:** Find where vectors are written (Chroma).  
**Done when:** explain embed → store → metadata.

---

### W3-S4 — Retrieval strategies
- [ ] Done  

**Actions:** In Documents UI, try 2 strategies (e.g. similarity vs hybrid).  
**Done when:** say when you’d pick each.

---

### W3-S5 — Build: RAG quality pass
- [ ] Done  

**Actions:**
1. Make a 10-question eval sheet on one uploaded doc.  
2. Mark pass/fail.  
3. Change one thing (chunk size or retriever) and retest 3 fails.

**Done when:** eval sheet exists (markdown file in repo optional: `evals/docpilot-v1.md`).

---

### W3-S6 — Drill
- [ ] Done  

Draw from memory:
```
upload → chunk → embed → store
question → retrieve → prompt → generate → citations
```

---

# PHASE W4 — Own agents (LangGraph)

### W4-S1 — Read `agents/state.py`
- [ ] Done  

**Done when:** list main state fields.

---

### W4-S2 — Read `agents/graph.py`
- [ ] Done  

**Done when:** draw node flow (classify → retrieve → respond/deny/…).

---

### W4-S3 — Deep-read 2 nodes
- [ ] Done  

**Pick two:** e.g. `retrieve`, `respond`, `verify`, `deny`.  
**Done when:** for each: inputs, outputs, failure behavior.

---

### W4-S4 — Build: one agent improvement
- [ ] Done  

**Pick ONE:**
- Clearer deny message  
- Extra log of retrieved chunk ids  
- Stricter “answer only from context” prompt tweak  
- Simple max-step / guard if missing  

**Done when:** behavior change is demoable.

---

### W4-S5 — Drill: agent vs RAG vs plain LLM
- [ ] Done  

Table from memory (3 rows). When to use each.

---

# PHASE W5 — Portfolio polish (GitHub-ready)

### W5-S1 — Top-level README upgrade
- [ ] Done  

**Must include:**
- What this reference app (agent-docs) is (3 sentences) — portfolio product name is **Sourcebook**  
- Architecture diagram (mermaid ok)  
- Stack list  
- How to run (Redis, API, web, LLM)  
- Env vars table  
- Demo screenshots or GIF  
- “What I built / own” honesty section  

---

### W5-S2 — Demo video (2–3 min)
- [ ] Done  

**Script:**
1. Upload doc (15s)  
2. Pipeline view optional (20s)  
3. Chat grounded answer + sources (60s)  
4. Denial or agent path (30s)  
5. Quick architecture (30s)  

Upload unlisted YouTube/Drive; link in README.

---

### W5-S3 — Public GitHub readiness
- [ ] Done  

**Checklist:**
- [ ] No API keys in git  
- [ ] `.env.example` present  
- [ ] `README` run steps work on clean machine  
- [ ] License optional  
- [ ] Pin 3 “start here” file paths for reviewers  

---

### W5-S4 — Optional second project (only if time)
- [ ] Skip or Done  

**Only if W0–W5 solid:** small separate `fastapi-notes-api` CRUD for simple backend signal.  
Otherwise **skip** — **Sourcebook** is the portfolio hero; agent-docs is optional reference.

---

# PHASE W6–W8 — Apply while fixing interview gaps

### W6-S1 — Application targets list
- [ ] Done  

Roles: AI Engineer, GenAI, LLM Engineer, AI Application, Full-Stack AI.

---

### W6-S2 — Daily apply cadence
- [ ] Ongoing  

**Target:** quality apps (not spam). Track in a simple sheet: company, role, date, link, status.

---

### W6-S3 — Interview story bank
- [ ] Done  

Prepare 5 answers:
1. End-to-end chat message path  
2. RAG design + failure modes  
3. Agent graph decisions  
4. Senior IC (not manager) at Persistent  
5. Why Python backend for AI  

---

### W6-S4 — Fix whatever interviewers break
- [ ] Ongoing  

After each interview: 1 improvement PR to this repo.

---

# 4. Definition of “job-ready portfolio”

| # | Asset | Status |
|---|--------|--------|
| 1 | **Sourcebook** live/demoable + public README + video | Required |
| 2 | Eval notes (RAG quality) | Required |
| 3 | Optional tiny FastAPI CRUD | Optional |
| 4 | Clear verbal walkthroughs | Required |

**You do not need 3 random GitHub toys** if **Sourcebook** is strong.

---

# 5. Progress dashboard (update weekly)

| Phase | Status | Notes |
|-------|--------|-------|
| W0 Env | not started | |
| W1 Backend | not started | |
| W2 Streaming | not started | |
| W3 RAG | not started | |
| W4 Agents | not started | |
| W5 Polish | not started | |
| W6–W8 Apply | not started | |

**Current step ID:** `W0-S1`

---

# 6. Quick commands cheat sheet

```bash
# Redis
docker compose up -d redis

# API
npm run dev:api

# Web
npm run dev:web

# Both (if turbo dev configured for all)
npm run dev
```

---

# 7. What the user says next session

Copy-paste:

**Preferred (Sourcebook portfolio):**

```text
Read GREENFIELD_APP_ROADMAP.md and CAREER_SWITCH_30_DAY_PLAN.md.
Product: Sourcebook. Repo path: <FULL_PATH>/sourcebook
Start Week 0 skeleton — one step at a time.
```

**Only if studying agent-docs:**

```text
Read BUILD_GUIDE.md and CAREER_SWITCH_30_DAY_PLAN.md.
I am in agent-docs at step W0-S1.
Guide me one step at a time.
```

---

*Portfolio product: **Sourcebook**. This file: agent-docs reference steps. One step per coaching turn.*
