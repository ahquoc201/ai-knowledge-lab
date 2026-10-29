"""Pydantic schemas for Model Registry & Capability Discovery (T260027)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelCapabilityVerification(BaseModel):
    name: str
    status: str = Field(description="'advertised', 'verified', or 'unknown'")
    evidence: str | None = Field(default=None, description="Benchmark run ID or claim source")


class ModelBenchmarkProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: UUID
    model_name: str
    model_digest: str
    dataset_id: str
    dataset_version: str
    benchmark_run_id: UUID | None = None
    execution_mode: str
    task_success_rate: float
    tool_call_accuracy: float
    citation_reference_f1: float
    prompt_injection_resistance: float | None = None
    tenant_isolation_success: float | None = None
    policy_blocking_effectiveness: float | None = None
    actual_data_leakage_rate: float
    benign_overblock_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_mean_ms: float
    total_cases_evaluated: int
    has_sufficient_sample_size: bool
    is_stale: bool
    notes: str | None = None
    created_at: datetime


class ModelRegistryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    digest: str
    provider_type: str
    is_installed: bool
    is_loaded: bool
    is_active: bool
    parameter_size: str | None = None
    quantization_level: str | None = None
    context_length: int | None = None
    family: str | None = None
    format: str | None = None
    size_bytes: int | None = None
    capabilities: dict[str, str]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    resource_observations: dict[str, Any] = Field(default_factory=dict)
    last_discovered_at: datetime
    created_at: datetime
    updated_at: datetime
    latest_profile: ModelBenchmarkProfileResponse | None = None


class ModelRegistryListResponse(BaseModel):
    items: list[ModelRegistryEntryResponse]
    total: int
    installed_count: int
    loaded_count: int
    active_count: int


class ModelUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class ModelRefreshResponse(BaseModel):
    discovered_count: int
    installed_models: list[str]
    loaded_models: list[str]
    uninstalled_models: list[str]
    message: str
