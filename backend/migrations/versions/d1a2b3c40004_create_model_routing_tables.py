"""create model routing policies and decisions tables

Revision ID: d1a2b3c40004
Revises: c9f5e1b30003
Create Date: 2026-10-29 11:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c40004'
down_revision: str | Sequence[str] | None = 'c9f5e1b30003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add model_name column to agent_runs
    op.add_column('agent_runs', sa.Column('model_name', sa.String(length=100), nullable=True))

    # 2. Create model_routing_policies table
    op.create_table(
        'model_routing_policies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('version', sa.String(length=30), server_default='v1.0', nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('default_model', sa.String(length=100), nullable=False),
        sa.Column('allowed_models', sa.JSON(), nullable=False),
        sa.Column('fallback_models', sa.JSON(), nullable=False),
        sa.Column('max_fallback_attempts', sa.Integer(), server_default='2', nullable=False),
        sa.Column('task_rules', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_model_routing_policies_workspace', 'model_routing_policies', ['workspace_id'])

    # 3. Create model_routing_decisions table
    op.create_table(
        'model_routing_decisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=True),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('policy_id', sa.UUID(), nullable=True),
        sa.Column('policy_version', sa.String(length=30), nullable=False),
        sa.Column('selected_model', sa.String(length=100), nullable=False),
        sa.Column('candidate_evaluations', sa.JSON(), nullable=False),
        sa.Column('selection_reason', sa.Text(), nullable=False),
        sa.Column('fallback_occurred', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('fallback_chain', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('latency_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('context_metadata', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['policy_id'], ['model_routing_policies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_routing_decisions_workspace_created', 'model_routing_decisions', ['workspace_id', 'created_at'])
    op.create_index('ix_routing_decisions_task_type', 'model_routing_decisions', ['task_type'])


def downgrade() -> None:
    op.drop_index('ix_routing_decisions_task_type', table_name='model_routing_decisions')
    op.drop_index('ix_routing_decisions_workspace_created', table_name='model_routing_decisions')
    op.drop_table('model_routing_decisions')
    op.drop_index('ix_model_routing_policies_workspace', table_name='model_routing_policies')
    op.drop_table('model_routing_policies')
    op.drop_column('agent_runs', 'model_name')
