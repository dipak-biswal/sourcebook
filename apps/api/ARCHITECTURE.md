# Agents package layout

All agent code lives under `app/agents/`, split by agent role:

```text
app/agents/
├── __init__.py                 # re-exports run_agent, approve_agent_run
│
├── context/                    # Workspace Context agent (pre-main)
│   ├── readiness.py            # pure gap assessment (packet + goal)
│   ├── questions.py            # template form builders
│   ├── llm.py                  # small-LLM question phrasing
│   ├── merge.py                # answers → COLLECTED RUN CONTEXT
│   └── phase.py                # start/resume HITL questions
│
├── main/                       # Main workspace agent
│   ├── profiles.py             # system prompts / tool allowlists
│   ├── tool_policy.py
│   ├── tools/                  # date, web_search, fetch_url, factory
│   ├── runner/                 # tool loop, HITL, lifecycle, events
│   ├── trace/                  # execution_trace
│   └── storage/                # run compact / prune
│
└── visual_summary/             # Visual Summary agent
    ├── tools.py                # plan_layout / render_ui LangChain tools
    ├── pipeline.py             # after “View in UI”
    ├── context.py
    ├── llm_json.py
    ├── blocks/                 # registry + gen_ui models
    ├── handoff/                # extract, structured, evidence
    ├── planning/               # ui_intent, layout, stabilize, validator
    ├── render/                 # assemble, engine, answer
    └── workspace/              # workspace context, profile, interactions
```

## Imports

| Use case | Import from |
|----------|-------------|
| Start / approve a run | `app.agents` or `app.agents.main.runner` |
| Build main tools | `app.agents.main.tools` |
| Context readiness / HITL | `app.agents.context` |
| Visual pipeline | `app.agents.visual_summary.pipeline` |
| Layout stabilize | `app.agents.visual_summary.planning.layout_stabilize` |
| GenUI models | `app.agents.visual_summary.blocks.gen_ui` |
| Block registry | `app.agents.visual_summary.blocks.registry` |

## Flow

```text
routers/agents.py
  → agents.main.runner
       → agents.context.phase   # if gaps → HITL questions, then resume
       → main tool loop + write/presentation HITL
  → agents.visual_summary.pipeline   # after presentation approve
       → handoff → planning → render
```
