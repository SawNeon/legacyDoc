"""Admin flag on users and the audit trail for account actions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_admin_audit"
down_revision: str | None = "0003_document_depth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("target_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("value_before", sa.String(length=120), nullable=True),
        sa.Column("value_after", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_admin_actions_target", "admin_actions", ["target_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_actions_target", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_column("users", "is_admin")
