# Agent & Visual Summary package layout

Backend code is split by **pipeline role**, not product vertical.

```text
app/
├── agents/                    # Main workspace agent
│   ├── profiles.py            # System prompts / tool allowlists
│   ├── tool_policy.py
│   ├── tools/                 # date, web_search, fetch_url, factory (build_tools)
│   ├── runner/                # Tool loop, HITL, lifecycle, events
│   ├── trace/                 # execution_trace
│   └── storage/               # run compact / prune
│
└── visual_summary/            # Visual Summary domain (after “View in UI”)
    ├── tools.py               # plan_layout / render_ui LangChain tools + LLM plan
    ├── pipeline.py            # Orchestrator entry from runner
    ├── context.py             # PresentationContext
    ├── llm_json.py
    ├── blocks/                # registry + gen_ui models
    ├── handoff/               # extract, structured, evidence
    ├── planning/              # ui_intent, layout, stabilize, validator, planner
    ├── render/                # assemble, engine, answer
    └── workspace/             # workspace context, profile, interactions
```

## Import conventions

| Use case | Import from |
|----------|-------------|
| Start / approve a run | `app.agents.runner` |
| Build main tools | `app.agents.tools` |
| Visual plan / stabilize | `app.visual_summary.planning.*` |
| GenUI models | `app.visual_summary.blocks.gen_ui` |
| Block registry | `app.visual_summary.blocks.registry` (or shim `app.blocks`) |

**Compatibility shims** remain at old paths (`app.presentation.*`, `app.agents.visual_tools`, …) so gradual migration stays green. Prefer the new paths in new code.

## Flow

```text
routers/agents.py
  → agents.runner (main tool loop + HITL)
  → visual_summary.pipeline (after presentation approve)
       → handoff → planning → render
```
