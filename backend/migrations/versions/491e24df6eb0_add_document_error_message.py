"""add_document_error_message

Revision ID: 491e24df6eb0
Revises: c789571b2330
Create Date: 2026-10-14 00:51:50.551872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '491e24df6eb0'
down_revision: Union[str, Sequence[str], None] = 'c789571b2330'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_message column to documents table."""
    op.add_column(
        "documents",
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove error_message column from documents table."""
    op.drop_column(
        "documents",
        "error_message",
    )
