"""Shared constants for the agent runner."""

WRITE_TOOLS = frozenset({"create_note"})
PRESENTATION_TOOL = "generative_ui"

# Tools whose closures hold a SQLAlchemy Session bound to this request/run.
# Sessions aren't thread-safe, so these must never execute concurrently with
# each other — see read_tools._run_read_tool_batch.
DB_BOUND_READ_TOOLS = frozenset(
    {"list_documents", "search_documents", "read_document", "plan_layout", "render_ui"}
)
