"""Hybrid search: full-text tsvector column + GIN index on chunks.

Adds a generated STORED tsvector derived from chunks.content. Postgres
backfills existing rows on ADD COLUMN and maintains it automatically on
insert/update, so no application write path or re-ingest is needed.

The column is intentionally NOT mapped on models.Chunk — it is a
DB-side search structure used only by the keyword arm of retrieval, and
keeping it out of the ORM leaves the SQLite unit-test path untouched.

Revision ID: 003
Revises: 002
Create Date: 2026-07-15

"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
