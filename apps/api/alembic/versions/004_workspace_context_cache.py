"""Workspace context cache for the LLM workspace profiler.

Adds workspaces.context_cache (JSON, nullable) holding the derived
WorkspaceContextPacket plus a fingerprint of the inputs it was derived
from (name/description/tags/ready documents). The profiler recomputes
only when the fingerprint changes, keeping LLM calls off the hot path.

Revision ID: 004
Revises: 003
Create Date: 2026-07-16

"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("context_cache", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "context_cache")
