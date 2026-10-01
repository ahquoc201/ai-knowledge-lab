"""enable pgvector extension

Revision ID: 08a3adea5be9
Revises: 644a18c28e37
Create Date: 2026-10-01 11:45:04.245425

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '08a3adea5be9'
down_revision: str | Sequence[str] | None = '644a18c28e37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
