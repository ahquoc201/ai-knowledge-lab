
"""Add document processing lease metadata.

Revision ID: c789571b2330
Revises: 69ab36e9e17c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision: str = "c789571b2330"
down_revision: str | Sequence[str] | None = "69ab36e9e17c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add processing lease fields to documents."""

    op.add_column(
        "documents",
        sa.Column(
            "processing_run_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "processing_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove processing lease fields."""

    op.drop_column(
        "documents",
        "processing_heartbeat_at",
    )

    op.drop_column(
        "documents",
        "processing_started_at",
    )

    op.drop_column(
        "documents",
        "processing_run_id",
    )
