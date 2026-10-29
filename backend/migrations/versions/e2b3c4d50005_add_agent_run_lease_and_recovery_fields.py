"""add lease and recovery fields to agent_runs (T260028)

Revision ID: e2b3c4d50005
Revises: d1a2b3c40004
Create Date: 2026-10-29 16:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2b3c4d50005'
down_revision: str | Sequence[str] | None = 'd1a2b3c40004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('agent_runs', sa.Column('lease_token', sa.String(length=64), nullable=True))
    op.add_column('agent_runs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_runs', sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'agent_runs',
        sa.Column('recovery_attempts', sa.Integer(), server_default='0', nullable=False),
    )
    op.add_column(
        'agent_runs',
        sa.Column('max_recovery_attempts', sa.Integer(), server_default='3', nullable=False),
    )
    op.create_index('ix_agent_runs_lease_recovery', 'agent_runs', ['status', 'lease_expires_at'])


def downgrade() -> None:
    op.drop_index('ix_agent_runs_lease_recovery', table_name='agent_runs')
    op.drop_column('agent_runs', 'max_recovery_attempts')
    op.drop_column('agent_runs', 'recovery_attempts')
    op.drop_column('agent_runs', 'last_heartbeat_at')
    op.drop_column('agent_runs', 'lease_expires_at')
    op.drop_column('agent_runs', 'lease_token')
