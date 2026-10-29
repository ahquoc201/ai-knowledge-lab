"""create agent benchmark tables

Revision ID: b8e4f0a20002
Revises: a7c3e9d10001
Create Date: 2026-10-28 17:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e4f0a20002'
down_revision: str | Sequence[str] | None = 'a7c3e9d10001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'agent_benchmark_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('dataset_id', sa.String(length=100), nullable=False),
        sa.Column('dataset_version', sa.String(length=50), nullable=False),
        sa.Column('execution_mode', sa.String(length=30), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('embedding_model', sa.String(length=100), nullable=True),
        sa.Column('runtime_config', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='running', nullable=False),
        sa.Column('total_cases', sa.Integer(), server_default='0', nullable=False),
        sa.Column('passed_cases', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_cases', sa.Integer(), server_default='0', nullable=False),
        sa.Column('task_success_rate', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('tool_call_accuracy', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('citation_f1', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('security_blocking_rate', sa.Float(), nullable=True),
        sa.Column('benign_overblock_rate', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_p50_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_p95_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_mean_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('failure_summary', sa.JSON(), nullable=True),
        sa.Column('category_scores', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_agent_benchmark_runs_workspace_created',
        'agent_benchmark_runs',
        ['workspace_id', 'created_at'],
        unique=False,
    )

    op.create_table(
        'agent_benchmark_case_results',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('benchmark_run_id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.String(length=50), nullable=False),
        sa.Column('case_name', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('is_adversarial', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('failure_classification', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('tool_accuracy', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('citation_f1', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('grounding_score', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=False),
        sa.Column('sanitized_trace', sa.JSON(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['benchmark_run_id'], ['agent_benchmark_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_benchmark_case_results_run_case',
        'agent_benchmark_case_results',
        ['benchmark_run_id', 'case_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_benchmark_case_results_run_case', table_name='agent_benchmark_case_results')
    op.drop_table('agent_benchmark_case_results')
    op.drop_index('ix_agent_benchmark_runs_workspace_created', table_name='agent_benchmark_runs')
    op.drop_table('agent_benchmark_runs')
