# 30-Day Full-Stack AI Developer Transition Guide

> **Note (2026):** Career portfolio product is **Sourcebook** (`sourcebook` repo). See `GREENFIELD_APP_ROADMAP.md` + `CAREER_SWITCH_30_DAY_PLAN.md`.  
> **This guide** is optional deep-dive of the **agent-docs** reference codebase only.

> **Context:** React/Next frontend comfort zone. Use `agent-docs` to study **Python Backend**, **RAG**, and **Agent Orchestration** patterns — then implement cleanly in **Sourcebook**.

This guide helps you understand end-to-end flow in **agent-docs** for interviews; **ship Sourcebook**, not this monorepo as the primary portfolio.

---

## 🎯 Week 1: Backend Foundations (FastAPI)
*Goal: Understand how the API receives requests, validates data, and manages state.*

Since you know Next.js API routes, FastAPI will feel familiar but more structured. It relies heavily on Python type hints and Pydantic for validation (similar to Zod in TypeScript).

**Files to study:**
1. **`apps/api/main.py`**
   - **What to look for:** This is the entry point (like `app/layout.tsx` or `server.js`). Notice how routers are included (e.g., `/chat`, `/ingest`).
2. **`apps/api/chat/routes.py`**
   - **What to look for:** Look at how endpoints are defined (`@router.post`). Notice the dependency injection (e.g., `Depends()`) which FastAPI uses heavily.
3. **`apps/api/chat/storage/repository.py` & `client.py`**
   - **What to look for:** See how Redis is used to store chat sessions. In AI apps, LLMs are stateless, so the backend must manage conversation history manually.

**Interview Talking Point:** 
Be able to compare Next.js API routes vs. FastAPI. (e.g., "FastAPI's built-in Swagger UI and Pydantic validation make it incredibly robust for data-heavy AI applications compared to standard Node.js backends.")

---

## 🧠 Week 2: The RAG Pipeline (Data Layer)
*Goal: Understand how documents are processed so an AI can read them.*

RAG (Retrieval-Augmented Generation) is the core of modern enterprise AI. It's a pipeline that turns files into searchable numbers (vectors).

**Files to study (in `apps/api/ingestion/`):**
1. **`pipeline.py`**
   - **What to look for:** The orchestrator. Read this top-to-bottom to see the 4 steps: Load → Chunk → Embed → Store.
2. **`chunking/splitter.py` & `catalog.py`**
   - **What to look for:** LLMs have context limits. We can't feed a 500-page PDF at once. We break it into "chunks". Look at how text is split.
3. **`embeddings/vectorstore.py`**
   - **What to look for:** This is where text chunks are converted into vector embeddings (lists of numbers) and saved into ChromaDB.
4. **`retrieval/strategies.py`**
   - **What to look for:** When a user asks a question, how do we find the right chunks? Look at `similarity` (vector distance) vs `bm25` (keyword search).

**Interview Talking Point:**
"I designed a RAG pipeline that handles multiple chunking strategies and retrieval methods (Hybrid, MMR, BM25) to ensure high-relevance context injection."

---

## 🤖 Week 3: LangGraph & Agentic Workflows
*Goal: Understand how the AI actually "thinks" and routes tasks.*

Simple AI apps just send a prompt to an LLM. Agentic apps (like yours) use a state machine (LangGraph) to make decisions, use tools, or route to specific skills.

**Files to study (in `apps/api/agents/`):**
1. **`state.py`**
   - **What to look for:** `AgentState`. This is the shared memory object passed between every node in the graph (similar to a Redux store).
2. **`graph.py`**
   - **What to look for:** The blueprint of the agent. Trace the path: `classify` → `retrieve` → `validate` → `respond` (or `verify`). This graph defines the AI's logic flow.
3. **`verify/agent.py`** (Crucial for interviews!)
   - **What to look for:** Hallucination prevention. Look at how this node splits the LLM's answer into claims and verifies them against the retrieved chunks.
4. **`flashcard/agent.py` or `tutor/agent.py`**
   - **What to look for:** See how specialized prompts are used for different "intents".

**Interview Talking Point:**
"Instead of a basic LLM chain, I orchestrated an agentic workflow using LangGraph. This allowed me to build a cyclic graph with a 'verify' node that automatically detects and prunes hallucinations before streaming the response to the user."

---

## ⚡ Week 4: End-to-End Integration (The Bridge)
*Goal: Connect the Next.js frontend to the AI backend via Streaming.*

AI responses are slow. If you wait for the whole answer, the user stares at a spinner for 10 seconds. We use Server-Sent Events (SSE) to stream words one by one.

**Files to study:**
1. **Backend:** `apps/api/chat/service.py` (`stream_chat_response` function)
   - **What to look for:** How FastAPI yields chunks of data using `StreamingResponse`. Notice how it yields `{"content": "..."}` and eventually `{"citations": [...]}`.
2. **Frontend:** `apps/web/app/chat/page.tsx`
   - **What to look for:** The `fetch` call that consumes the `ReadableStream`. This is where your React expertise meets the AI backend.
3. **Generative UI:** `apps/web/app/chat/lib/gen-ui.ts`
   - **What to look for:** How you parse special tags (like ` ```flashcards `) from the LLM stream and render React components dynamically.

---

## 🚀 The Ultimate Interview Prep Task: Build Phase 0

To truly cement this knowledge, your goal for the next 30 days is to implement **Phase 0** from your roadmap: **Multi-tenancy**.

This touches every part of the stack:
1. **Frontend:** Pass the Auth.js user token/ID in API requests (`apps/web`).
2. **Backend:** Write a FastAPI middleware or dependency to decode the user ID (`apps/api`).
3. **Redis:** Change session keys from `agentdocs:chat:session:{id}` to `agentdocs:user:{user_id}:session:{id}`.
4. **ChromaDB:** Add a `user_id` metadata filter to vectors so users only search their own documents.

If you can build this, you are ready for a Full-Stack AI interview.

---

## Summary Checklist for End-to-End Flow
When an interview asks: *"Walk me through what happens when a user sends a message in your app,"* you should be able to say:

1. **Frontend:** React captures input and opens an SSE stream to FastAPI.
2. **API:** FastAPI receives it, loads past history from Redis.
3. **Agent (Classify):** LangGraph starts. The LLM classifies the intent (e.g., "Q&A" vs "Flashcards").
4. **Agent (Retrieve):** Embeds the question, searches ChromaDB for matching document chunks.
5. **Agent (Respond):** Injects chunks into the prompt, asks LLM for answer.
6. **Agent (Verify):** Checks if the LLM hallucinated.
7. **Streaming:** FastAPI streams the verified tokens back to Next.js.
8. **UI:** React renders the markdown and Generative UI components in real-time.
