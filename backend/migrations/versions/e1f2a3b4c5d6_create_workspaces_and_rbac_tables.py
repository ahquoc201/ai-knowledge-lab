"""create_workspaces_and_rbac_tables

Revision ID: e1f2a3b4c5d6
Revises: 491e24df6eb0
Create Date: 2026-10-14 22:55:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "491e24df6eb0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create workspaces table
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    # 2. Create workspace_memberships table
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=30),
            server_default="viewer",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
    )
    op.create_index(
        "ix_workspace_memberships_workspace_id",
        "workspace_memberships",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_memberships_user_id",
        "workspace_memberships",
        ["user_id"],
    )

    # 3. Create workspace_invitations table
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_invitations_token_hash",
        "workspace_invitations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_workspace_invitations_workspace_id",
        "workspace_invitations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_invitations_email",
        "workspace_invitations",
        ["email"],
    )

    # 4. Create security_audit_events table
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column(
            "outcome",
            sa.String(length=20),
            server_default="success",
            nullable=False,
        ),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_security_audit_events_workspace_id",
        "security_audit_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_security_audit_events_action",
        "security_audit_events",
        ["action"],
    )
    op.create_index(
        "ix_security_audit_events_created_at",
        "security_audit_events",
        ["created_at"],
    )

    # 5. Add workspace_id column to documents and conversations (initially nullable)
    op.add_column(
        "documents",
        sa.Column("workspace_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("workspace_id", sa.UUID(), nullable=True),
    )

    # 6. Legacy Data Backfill
    # Create a personal workspace for each existing user and assign documents/conversations
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO workspaces (id, name, slug, status, created_by, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                COALESCE(NULLIF(TRIM(full_name), ''), 'Personal') || '''s Workspace',
                'personal-' || id::text,
                'active',
                id,
                now(),
                now()
            FROM users
            ON CONFLICT (slug) DO NOTHING;
            """
        )
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO workspace_memberships (id, workspace_id, user_id, role, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                w.id,
                w.created_by,
                'owner',
                now(),
                now()
            FROM workspaces w
            WHERE w.created_by IS NOT NULL
            ON CONFLICT (workspace_id, user_id) DO NOTHING;
            """
        )
    )

    conn.execute(
        sa.text(
            """
            UPDATE documents d
            SET workspace_id = w.id
            FROM workspaces w
            WHERE w.created_by = d.user_id
              AND w.slug = 'personal-' || d.user_id::text
              AND d.workspace_id IS NULL;
            """
        )
    )

    conn.execute(
        sa.text(
            """
            UPDATE conversations c
            SET workspace_id = w.id
            FROM workspaces w
            WHERE w.created_by = c.user_id
              AND w.slug = 'personal-' || c.user_id::text
              AND c.workspace_id IS NULL;
            """
        )
    )

    # 7. Apply foreign key constraints, NOT NULL, and indexes
    op.create_foreign_key(
        "fk_documents_workspace_id",
        "documents",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_conversations_workspace_id",
        "conversations",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column("documents", "workspace_id", nullable=False)
    op.alter_column("conversations", "workspace_id", nullable=False)

    op.create_index(
        "ix_documents_workspace_id",
        "documents",
        ["workspace_id"],
    )
    op.create_index(
        "ix_conversations_workspace_id",
        "conversations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_workspace_id", table_name="conversations")
    op.drop_index("ix_documents_workspace_id", table_name="documents")

    op.drop_constraint("fk_conversations_workspace_id", "conversations", type_="foreignkey")
    op.drop_constraint("fk_documents_workspace_id", "documents", type_="foreignkey")

    op.drop_column("conversations", "workspace_id")
    op.drop_column("documents", "workspace_id")

    op.drop_table("security_audit_events")
    op.drop_table("workspace_invitations")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
