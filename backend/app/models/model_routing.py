"""SQLAlchemy ORM models for Model Routing Policies & Observability Decisions (T260027)."""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskType:
    SIMPLE_CHAT = "SIMPLE_CHAT"
    RAG_FACTUAL_QA = "RAG_FACTUAL_QA"
    RAG_MULTI_DOCUMENT_SYNTHESIS = "RAG_MULTI_DOCUMENT_SYNTHESIS"
    STRUCTURED_EXTRACTION = "STRUCTURED_EXTRACTION"
    AGENT_TOOL_SELECTION = "AGENT_TOOL_SELECTION"
    AGENT_MULTI_STEP_WORKFLOW = "AGENT_MULTI_STEP_WORKFLOW"
    AGENT_WRITE_PROPOSAL = "AGENT_WRITE_PROPOSAL"

    ALL: ClassVar[list[str]] = [
        SIMPLE_CHAT,
        RAG_FACTUAL_QA,
        RAG_MULTI_DOCUMENT_SYNTHESIS,
        STRUCTURED_EXTRACTION,
        AGENT_TOOL_SELECTION,
        AGENT_MULTI_STEP_WORKFLOW,
        AGENT_WRITE_PROPOSAL,
    ]


class ModelRoutingPolicy(Base):
    """Routing policy configuring model allowlist, default model, and scoring weights."""

    __tablename__ = "model_routing_policies"

    __table_args__ = (
        Index("ix_model_routing_policies_workspace", "workspace_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(30), server_default="v1.0", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    default_model: Mapped[str] = mapped_column(String(100), nullable=False)
    allowed_models: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    fallback_models: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    max_fallback_attempts: Mapped[int] = mapped_column(
        Integer, server_default="2", nullable=False
    )

    # Per-task rules and weights:
    # {
    #   "SIMPLE_CHAT": {"quality_weight": 0.5, "tool_weight": 0.0, "latency_weight": 0.5, "required_capabilities": ["chat"]},
    #   "AGENT_TOOL_SELECTION": {"quality_weight": 0.3, "tool_weight": 0.5, "latency_weight": 0.2, "required_capabilities": ["tools"]}
    # }
    task_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ModelRoutingDecision(Base):
    """Audit record capturing an individual model routing decision with rationale."""

    __tablename__ = "model_routing_decisions"

    __table_args__ = (
        Index("ix_routing_decisions_workspace_created", "workspace_id", "created_at"),
        Index("ix_routing_decisions_task_type", "task_type"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_routing_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    policy_version: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_model: Mapped[str] = mapped_column(String(100), nullable=False)

    # Detailed candidate evaluations:
    # [
    #   {"model": "qwen3:1.7b", "eligible": True, "score": 0.85, "reason": "Highest tool accuracy"},
    #   {"model": "unsupported:model", "eligible": False, "score": 0.0, "reason": "Missing verified tools capability"}
    # ]
    candidate_evaluations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    selection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_occurred: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    fallback_chain: Mapped[list[str]] = mapped_column(
        JSON, server_default="[]", nullable=False
    )
    latency_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)

    # Sanitized context metadata (NO raw prompt texts or confidential document bodies!)
    context_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default="{}", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
