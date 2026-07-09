Multi-tenant document AI workspace: upload files, grounded RAG chat with citations, and tool-using agents.

## Stack

- **API:** Python · FastAPI (`apps/api`)
- **Web:** React · Vite (`apps/web`)
- **Data:** Postgres + Redis (Docker Compose — optional until Week 1)

## Quick start

### API

```bash
cd apps/api
uv sync
uv run python main.py