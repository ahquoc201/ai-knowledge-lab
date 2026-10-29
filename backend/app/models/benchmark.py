"""SQLAlchemy ORM models for Agent Evaluation & Reliability Benchmarks (T260026)."""

from datetime import datetime
from typing import Any
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentBenchmarkRun(Base):
    """Persisted benchmark execution report scoped to a workspace."""

    __tablename__ = "agent_benchmark_runs"

    __table_args__ = (
        Index("ix_agent_benchmark_runs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), nullable=False)  # "simulated" | "real"
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), server_default="running", nullable=False
    )
    total_cases: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    failed_cases: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    task_success_rate: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    tool_call_accuracy: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    citation_f1: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    security_blocking_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    benign_overblock_rate: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_p50_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_p95_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_mean_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    failure_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    category_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    case_results: Mapped[list["AgentBenchmarkCaseResult"]] = relationship(
        "AgentBenchmarkCaseResult",
        back_populates="benchmark_run",
        cascade="all, delete-orphan",
        order_by="AgentBenchmarkCaseResult.created_at",
    )


class AgentBenchmarkCaseResult(Base):
    """Result of an individual test case evaluation within a benchmark run."""

    __tablename__ = "agent_benchmark_case_results"

    __table_args__ = (
        Index("ix_benchmark_case_results_run_case", "benchmark_run_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    benchmark_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_benchmark_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(50), nullable=False)
    case_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_adversarial: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_classification: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tool_accuracy: Mapped[float] = mapped_column(Float, server_default="1.0", nullable=False)
    citation_f1: Mapped[float] = mapped_column(Float, server_default="1.0", nullable=False)
    grounding_score: Mapped[float] = mapped_column(Float, server_default="1.0", nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    sanitized_trace: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    benchmark_run: Mapped["AgentBenchmarkRun"] = relationship(
        "AgentBenchmarkRun", back_populates="case_results"
    )
