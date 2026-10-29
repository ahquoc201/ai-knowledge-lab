"""SQLAlchemy ORM models for Model Registry and Capability Profiles (T260027)."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
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


class ModelCapabilityStatus:
    ADVERTISED = "advertised"
    VERIFIED = "verified"
    UNKNOWN = "unknown"


class ModelRegistryEntry(Base):
    """Registered LLM discovered from Ollama or authorized provider."""

    __tablename__ = "model_registry_entries"

    __table_args__ = (
        Index("ix_model_registry_name", "name", unique=True),
        Index("ix_model_registry_digest", "digest"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    digest: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(50), server_default="ollama", nullable=False
    )
    is_installed: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    is_loaded: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    parameter_size: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quantization_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    family: Mapped[str | None] = mapped_column(String(50), nullable=True)
    format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Capability verification mapping: {"tools": "verified", "chat": "verified", "structured_output": "advertised"}
    capabilities: Mapped[dict[str, str]] = mapped_column(
        JSON, server_default="{}", nullable=False
    )

    # Raw metadata from /api/show (architecture, parameters, template)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default="{}", nullable=False
    )

    # Runtime resource observations from /api/ps (vram_bytes, expires_at, etc.)
    resource_observations: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default="{}", nullable=False
    )

    last_discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    benchmark_profiles: Mapped[list["ModelBenchmarkProfile"]] = relationship(
        "ModelBenchmarkProfile",
        back_populates="model_entry",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ModelBenchmarkProfile.created_at.desc()",
    )


class ModelBenchmarkProfile(Base):
    """Historical and aggregated benchmark evaluation profile for a model version."""

    __tablename__ = "model_benchmark_profiles"

    __table_args__ = (
        Index("ix_model_benchmark_profiles_model_digest", "model_id", "model_digest"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_registry_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    benchmark_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_benchmark_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_mode: Mapped[str] = mapped_column(
        String(30), server_default="real", nullable=False
    )

    task_success_rate: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    tool_call_accuracy: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    citation_reference_f1: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    prompt_injection_resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenant_isolation_success: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_blocking_effectiveness: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_data_leakage_rate: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    benign_overblock_rate: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_p50_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_p95_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)
    latency_mean_ms: Mapped[float] = mapped_column(Float, server_default="0.0", nullable=False)

    total_cases_evaluated: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    has_sufficient_sample_size: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    is_stale: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model_entry: Mapped["ModelRegistryEntry"] = relationship(
        "ModelRegistryEntry", back_populates="benchmark_profiles"
    )
