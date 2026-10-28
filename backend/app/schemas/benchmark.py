"""Pydantic schemas for Agent Reliability Benchmarks (T260026)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Agent Reliability Benchmark", max_length=150)
    dataset_id: str = Field(default="agent_reliability_core", max_length=100)
    execution_mode: str = Field(default="simulated", pattern="^(simulated|real)$")
    model_name: str | None = Field(default=None, max_length=100)
    category_filter: str | None = Field(default=None, max_length=50)


class BenchmarkCaseResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    benchmark_run_id: UUID
    case_id: str
    case_name: str
    category: str
    is_adversarial: bool
    passed: bool
    failure_classification: str
    score: float
    reason: str
    tool_accuracy: float
    citation_f1: float
    grounding_score: float
    latency_ms: float
    sanitized_trace: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    created_at: datetime


class BenchmarkRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_by: UUID
    name: str
    dataset_id: str
    dataset_version: str
    execution_mode: str
    model_name: str
    embedding_model: str | None = None
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    task_success_rate: float
    tool_call_accuracy: float
    citation_f1: float
    security_blocking_rate: float | None = None
    benign_overblock_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_mean_ms: float
    created_at: datetime
    completed_at: datetime | None = None


class BenchmarkRunResponse(BenchmarkRunSummary):
    runtime_config: dict[str, Any]
    failure_summary: dict[str, Any] | None = None
    category_scores: dict[str, Any] | None = None
    case_results: list[BenchmarkCaseResultResponse] = Field(default_factory=list)


class BenchmarkRunListResponse(BaseModel):
    items: list[BenchmarkRunSummary]
    total: int


class MetricDelta(BaseModel):
    current: float
    baseline: float
    delta: float
    improved: bool


class BenchmarkComparisonResponse(BaseModel):
    current_run_id: UUID
    baseline_run_id: UUID
    current_model: str
    baseline_model: str
    current_mode: str
    baseline_mode: str
    task_success_rate: MetricDelta
    tool_call_accuracy: MetricDelta
    citation_f1: MetricDelta
    latency_p50_ms: MetricDelta
    security_blocking_rate: MetricDelta | None = None
    newly_failing_cases: list[str] = Field(default_factory=list)
    newly_passing_cases: list[str] = Field(default_factory=list)
