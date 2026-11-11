"""add functional GIN index for full-text search to document_chunks (T260032)

Revision ID: f3c4d5e60006
Revises: e2b3c4d50005
Create Date: 2026-11-11 11:45:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3c4d5e60006'
down_revision: str | Sequence[str] | None = 'e2b3c4d50005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: create functional GIN index for full-text search."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsvector "
        "ON document_chunks USING gin (to_tsvector('simple', content))"
    )


def downgrade() -> None:
    """Downgrade schema: drop functional GIN index."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsvector")
