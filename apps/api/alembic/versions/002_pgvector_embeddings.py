"""Move chunk embeddings from JSON to pgvector + HNSW index.

Also adds chunks.embedding_model so vectors from different embedding
models are never mixed at query time.

Dimensions are frozen at 1536 (text-embedding-3-small) — the model in
production when this migration was written. A future model switch needs
a new migration (and re-ingest).

Revision ID: 002
Revises: 001
Create Date: 2026-07-15

"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

DIM = 1536


def _current_embedding_model() -> str:
    from app.config import settings

    return settings.embedding_model


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding_vec vector({DIM})")
    # JSON arrays serialize as '[0.1, 0.2, ...]', which pgvector parses directly
    op.execute(
        f"""
        UPDATE chunks
        SET embedding_vec = embedding::text::vector({DIM})
        WHERE embedding IS NOT NULL
          AND json_array_length(embedding::json) = {DIM}
        """
    )
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE chunks RENAME COLUMN embedding_vec TO embedding")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.add_column(
        "chunks", sa.Column("embedding_model", sa.String(120), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE chunks SET embedding_model = :model WHERE embedding IS NOT NULL"
        ).bindparams(model=_current_embedding_model())
    )


def downgrade() -> None:
    op.drop_column("chunks", "embedding_model")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_json json")
    op.execute(
        "UPDATE chunks SET embedding_json = embedding::text::json "
        "WHERE embedding IS NOT NULL"
    )
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE chunks RENAME COLUMN embedding_json TO embedding")
