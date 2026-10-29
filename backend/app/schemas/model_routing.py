"""Pydantic schemas for Model Routing Policies, Decisions and Previews (T260027)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskRule(BaseModel):
    quality_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    tool_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    required_capabilities: list[str] = Field(default_factory=list)


class ModelRoutingPolicyBase(BaseModel):
    name: str = Field(..., max_length=100)
    version: str = Field(default="v1.0", max_length=30)
    is_enabled: bool = True
    default_model: str = Field(..., max_length=100)
    allowed_models: list[str] = Field(default_factory=list)
    fallback_models: list[str] = Field(default_factory=list)
    max_fallback_attempts: int = Field(default=2, ge=0, le=5)
    task_rules: dict[str, Any] = Field(default_factory=dict)


class ModelRoutingPolicyCreate(ModelRoutingPolicyBase):
    workspace_id: UUID | None = None


class ModelRoutingPolicyUpdate(BaseModel):
    name: str | None = None
    is_enabled: bool | None = None
    default_model: str | None = None
    allowed_models: list[str] | None = None
    fallback_models: list[str] | None = None
    max_fallback_attempts: int | None = None
    task_rules: dict[str, Any] | None = None


class ModelRoutingPolicyRead(ModelRoutingPolicyBase):
    id: UUID
    workspace_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateEvaluation(BaseModel):
    model: str
    eligible: bool
    score: float
    reason: str


class ModelRoutingPreviewRequest(BaseModel):
    workspace_id: UUID | None = None
    prompt: str = Field(..., min_length=1)
    has_retrieved_context: bool = False
    context_document_count: int = 0
    requires_tools: bool = False
    is_write_operation: bool = False
    explicit_task_type: str | None = None


class ModelRoutingPreviewResponse(BaseModel):
    task_type: str
    selected_model: str
    selection_reason: str
    fallback_chain: list[str]
    candidate_evaluations: list[CandidateEvaluation]
    policy_id: UUID | None = None
    policy_version: str


class ModelRoutingDecisionRead(BaseModel):
    id: UUID
    workspace_id: UUID | None
    task_type: str
    policy_id: UUID | None
    policy_version: str
    selected_model: str
    candidate_evaluations: list[dict[str, Any]]
    selection_reason: str
    fallback_occurred: bool
    fallback_chain: list[str]
    latency_ms: float
    context_metadata: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
