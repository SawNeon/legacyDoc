"""Pricing rules, credit grants and overflow settlement."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_billing_credits"
down_revision: str | None = "0005_job_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fx_rate_brl_per_usd", sa.Float(), nullable=False),
        sa.Column("fees_tax_percent", sa.Float(), nullable=False),
        sa.Column("topup_credit_ratio", sa.Float(), nullable=False),
        sa.Column("topup_cost_ratio", sa.Float(), nullable=False),
        sa.Column("topup_validity_months", sa.Integer(), nullable=False),
        sa.Column(
            "topup_pack_prices_brl",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("near_limit_percent", sa.Float(), nullable=False),
        sa.Column("min_margin_alert_percent", sa.Float(), nullable=False),
        sa.Column("typical_usage_percent", sa.Float(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "plan_pricing",
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("price_brl", sa.Float(), nullable=False),
        sa.Column("credits_brl", sa.Float(), nullable=False),
        sa.Column("cost_ratio", sa.Float(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("tier"),
    )

    op.create_table(
        "credit_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credits_brl", sa.Float(), nullable=False),
        sa.Column("ceiling_usd", sa.Float(), nullable=False),
        sa.Column("remaining_usd", sa.Float(), nullable=False),
        sa.Column("price_paid_brl", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_grants_user_expires", "credit_grants", ["user_id", "expires_at"])

    op.create_table(
        "usage_settlements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("settled_usd", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "period"),
    )


def downgrade() -> None:
    op.drop_table("usage_settlements")
    op.drop_index("ix_credit_grants_user_expires", table_name="credit_grants")
    op.drop_table("credit_grants")
    op.drop_table("plan_pricing")
    op.drop_table("billing_settings")
