# Learning workspaces & study boards

How Sourcebook turns a **learning workspace** (e.g. “System Design”) into topic cards, a streamed teaching answer, and a progressive **study board** Visual Summary.

## User path

1. Create a workspace with a learning-oriented name/description (or tag `learning`).
2. Open **Agents** → topic catalog loads (web + small LLM, with fallbacks).
3. Pick a topic (or add a custom one; off-topic titles are declined).
4. Answer **checkbox-only** intake (level, focus, format, scope).
5. **Start study run** — goal is composed from topic + preferences.
6. While the main agent writes numbered `## N.` sections:
   - **Answer** tab shows closed sections live.
   - **Visual** tab paints panels early (text first, then diagrams).
7. On complete, study boards often **skip** presentation HITL when a board already exists.
8. Optional: enable draw.io MCP for rich diagram enrich; **Rebuild visual** for a full re-run.

## Settings

- **Workspaces** → active topics, **archive** / **restore**.
- Curriculum is stored on `workspaces.curriculum` (JSON).

## Migration

```bash
cd apps/api && uv run alembic upgrade head
```

Requires revision **007** (`workspace.curriculum` column).

## Architecture (short)

| Module | Role |
|--------|------|
| `app/curriculum/` | Domain detect, discover, validate custom, intake, compose goal |
| `section_stream.py` | Parse closed `## N.` sections mid-answer; SSE `section_draft` |
| `early_visual.py` | Code-assemble study panels while answer streams; optional MCP enrich |
| `streaming/progressive.py` | Panel-by-panel assemble (text → figure merge) |
| Visual blocks | `flow_diagram`, `sequence_diagram`, `compare_paths`, composite prose |

Main agent still owns facts; Visual / early visual only present structured content.

## Related

- [`visual_summary.md`](./visual_summary.md) — overall Visual Summary pipeline
- [`agent_execution_model.md`](./agent_execution_model.md) — phases of one `AgentRun`
