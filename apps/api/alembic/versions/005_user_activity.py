"""Track user login and last-seen for monitoring.

Adds users.last_login_at and users.last_seen_at so the Settings Monitoring
tab can show who is online and recently active.

Revision ID: 005
Revises: 004
Create Date: 2026-07-21

"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "last_login_at")
