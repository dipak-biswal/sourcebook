"""Store per-run agent options (e.g. enabled MCP connectors).

Revision ID: 006
Revises: 005
Create Date: 2026-07-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    json_type = JSONB() if dialect == "postgresql" else sa.JSON()
    op.add_column(
        "agent_runs",
        sa.Column("run_options", json_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "run_options")
