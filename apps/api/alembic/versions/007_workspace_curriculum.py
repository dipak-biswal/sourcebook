"""Workspace curriculum JSON (topic catalog + preferences).

Revision ID: 007
Revises: 006
Create Date: 2026-07-26

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    json_type = JSONB() if dialect == "postgresql" else sa.JSON()
    op.add_column(
        "workspaces",
        sa.Column("curriculum", json_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "curriculum")
