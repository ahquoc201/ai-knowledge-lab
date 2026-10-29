"""create model registry and benchmark profile tables

Revision ID: c9f5e1b30003
Revises: b8e4f0a20002
Create Date: 2026-10-29 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9f5e1b30003'
down_revision: str | Sequence[str] | None = 'b8e4f0a20002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'model_registry_entries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('digest', sa.String(length=128), nullable=False),
        sa.Column('provider_type', sa.String(length=50), server_default='ollama', nullable=False),
        sa.Column('is_installed', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_loaded', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('parameter_size', sa.String(length=30), nullable=True),
        sa.Column('quantization_level', sa.String(length=30), nullable=True),
        sa.Column('context_length', sa.Integer(), nullable=True),
        sa.Column('family', sa.String(length=50), nullable=True),
        sa.Column('format', sa.String(length=30), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('capabilities', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('metadata_json', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('resource_observations', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('last_discovered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_model_registry_name', 'model_registry_entries', ['name'], unique=True)
    op.create_index('ix_model_registry_digest', 'model_registry_entries', ['digest'])

    op.create_table(
        'model_benchmark_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('model_id', sa.UUID(), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('model_digest', sa.String(length=128), nullable=False),
        sa.Column('dataset_id', sa.String(length=100), nullable=False),
        sa.Column('dataset_version', sa.String(length=50), nullable=False),
        sa.Column('benchmark_run_id', sa.UUID(), nullable=True),
        sa.Column('execution_mode', sa.String(length=30), server_default='real', nullable=False),
        sa.Column('task_success_rate', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('tool_call_accuracy', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('citation_reference_f1', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('prompt_injection_resistance', sa.Float(), nullable=True),
        sa.Column('tenant_isolation_success', sa.Float(), nullable=True),
        sa.Column('policy_blocking_effectiveness', sa.Float(), nullable=True),
        sa.Column('actual_data_leakage_rate', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('benign_overblock_rate', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_p50_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_p95_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('latency_mean_ms', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('total_cases_evaluated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('has_sufficient_sample_size', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_stale', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['benchmark_run_id'], ['agent_benchmark_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['model_id'], ['model_registry_entries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_model_benchmark_profiles_model_id', 'model_benchmark_profiles', ['model_id'])
    op.create_index('ix_model_benchmark_profiles_model_digest', 'model_benchmark_profiles', ['model_id', 'model_digest'])


def downgrade() -> None:
    op.drop_index('ix_model_benchmark_profiles_model_digest', table_name='model_benchmark_profiles')
    op.drop_index('ix_model_benchmark_profiles_model_id', table_name='model_benchmark_profiles')
    op.drop_table('model_benchmark_profiles')
    op.drop_index('ix_model_registry_digest', table_name='model_registry_entries')
    op.drop_index('ix_model_registry_name', table_name='model_registry_entries')
    op.drop_table('model_registry_entries')
