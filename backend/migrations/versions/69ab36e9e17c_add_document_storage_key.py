"""Add document storage key.

Revision ID: 69ab36e9e17c
Revises: 11219df49abf
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "69ab36e9e17c"
down_revision: str | Sequence[str] | None = "11219df49abf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "storage_key",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "documents",
        "storage_key",
    )