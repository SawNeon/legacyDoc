"""Record which analysis depth produced each document."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_document_depth"
down_revision: str | None = "0002_reset_lockout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("depth", sa.String(length=20), nullable=False, server_default="basic"),
    )


def downgrade() -> None:
    op.drop_column("documents", "depth")
