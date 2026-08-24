"""Track the latest accepted snapshot per source.

Revision ID: 20260824_0002
Revises: 20260824_0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0002"
down_revision: str | Sequence[str] | None = "20260824_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("last_snapshot_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "last_snapshot_at")
