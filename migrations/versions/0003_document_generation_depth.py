"""Record which analysis depth produced each document.

Revision ID: 0003_document_depth
Revises: 0002_reset_lockout
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_document_depth"
down_revision: str | None = "0002_reset_lockout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default is required or ALTER TABLE fails on existing rows. Rows
    # written before this column existed are labelled "basic": understating
    # what a document received is safer than claiming an audit that never ran.
    op.add_column(
        "documents",
        sa.Column("depth", sa.String(length=20), nullable=False, server_default="basic"),
    )


def downgrade() -> None:
    op.drop_column("documents", "depth")
