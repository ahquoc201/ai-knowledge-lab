"""Pydantic schemas for the Governed Agent Runtime API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    allowed_tools: list[str] | None = None
    correlation_id: str | None = Field(default=None, max_length=64)


class AgentStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_index: int
    tool_name: str
    side_effect: str | None
    reason: str | None
    arguments: dict[str, Any] | None
    status: str
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class AgentApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_id: UUID
    workspace_id: UUID
    requested_by: UUID
    tool_name: str
    payload: dict[str, Any]
    payload_hash: str
    status: str
    decided_by: UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    expires_at: datetime
    created_at: datetime


class AgentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    seq: int
    event_type: str
    step_id: UUID | None
    data: dict[str, Any] | None
    created_at: datetime


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    initiated_by: UUID
    goal: str
    model_name: str | None = None
    status: str
    status_reason: str | None
    current_step: int
    tool_call_count: int
    denial_count: int
    max_steps: int
    max_tool_calls: int
    allowed_tools: list[str]
    cancel_requested: bool
    final_answer: str | None
    sources: list[dict[str, Any]] | None
    error_code: str | None
    error_message: str | None
    deadline_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    pending_approval: AgentApprovalResponse | None = None
    steps: list[AgentStepResponse] | None = None


class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int
    limit: int
    offset: int


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
