"""API endpoints for Model Routing Policy, Preview and Observability (T260027)."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.repositories.workspace_membership import get_membership
from app.schemas.model_routing import (
    CandidateEvaluation,
    ModelRoutingDecisionRead,
    ModelRoutingPolicyRead,
    ModelRoutingPolicyUpdate,
    ModelRoutingPreviewRequest,
    ModelRoutingPreviewResponse,
)
from app.services.model_router import ModelRouter
from app.services.task_classifier import TaskClassifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-routing", tags=["model-routing"])


@router.get("/policies", response_model=ModelRoutingPolicyRead)
async def get_routing_policy(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[UUID | None, Query()] = None,
) -> ModelRoutingPolicyRead:
    """Get active model routing policy for workspace or default system policy."""
    is_super = getattr(current_user, "is_superuser", False)
    if workspace_id is not None and not is_super:
        member = await get_membership(session, workspace_id=workspace_id, user_id=current_user.id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace.",
            )

    model_router = ModelRouter()
    policy = await model_router.get_or_create_policy(session, workspace_id)
    return ModelRoutingPolicyRead.model_validate(policy)


@router.put("/policies/{policy_id}", response_model=ModelRoutingPolicyRead)
async def update_routing_policy(
    policy_id: UUID,
    payload: ModelRoutingPolicyUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ModelRoutingPolicyRead:
    """Update model routing policy (Requires Superuser or Workspace Admin/Owner)."""
    model_router = ModelRouter()
    stmt_policy = await model_router.update_policy(
        session=session,
        policy_id=policy_id,
        update_data=payload.model_dump(exclude_unset=True),
    )
    if not stmt_policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing policy '{policy_id}' not found.",
        )

    # Permission check
    is_super = getattr(current_user, "is_superuser", False)
    if stmt_policy.workspace_id is not None and not is_super:
        member = await get_membership(session, workspace_id=stmt_policy.workspace_id, user_id=current_user.id)
        if not member or member.role.lower() not in ["owner", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only workspace OWNER or ADMIN can modify routing policy.",
            )
    elif stmt_policy.workspace_id is None and not is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superuser can modify global routing policy.",
        )

    return ModelRoutingPolicyRead.model_validate(stmt_policy)


@router.post("/preview", response_model=ModelRoutingPreviewResponse)
async def preview_routing(
    payload: ModelRoutingPreviewRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ModelRoutingPreviewResponse:
    """Preview model routing decision without executing LLM call or writing decision logs."""
    is_super = getattr(current_user, "is_superuser", False)
    if payload.workspace_id is not None and not is_super:
        member = await get_membership(session, workspace_id=payload.workspace_id, user_id=current_user.id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace.",
            )

    # Determine task type
    if payload.explicit_task_type:
        task_type = payload.explicit_task_type
    else:
        classifier = TaskClassifier()
        task_type = classifier.classify(
            prompt=payload.prompt,
            has_retrieved_context=payload.has_retrieved_context,
            context_document_count=payload.context_document_count,
            requires_tools=payload.requires_tools,
            is_write_operation=payload.is_write_operation,
        )

    model_router = ModelRouter()
    decision = await model_router.preview_routing(
        session=session,
        task_type=task_type,
        workspace_id=payload.workspace_id,
    )

    return ModelRoutingPreviewResponse(
        task_type=decision.task_type,
        selected_model=decision.selected_model,
        selection_reason=decision.selection_reason,
        fallback_chain=decision.fallback_chain,
        candidate_evaluations=[
            CandidateEvaluation(
                model=c.model_name,
                eligible=c.eligible,
                score=c.score,
                reason=c.reason,
            )
            for c in decision.candidate_evaluations
        ],
        policy_id=decision.policy_id,
        policy_version=decision.policy_version,
    )


@router.get("/decisions", response_model=list[ModelRoutingDecisionRead])
async def list_routing_decisions(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[UUID | None, Query()] = None,
    task_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ModelRoutingDecisionRead]:
    """List historical model routing decisions for observability and audit trails."""
    is_super = getattr(current_user, "is_superuser", False)
    if workspace_id is not None and not is_super:
        member = await get_membership(session, workspace_id=workspace_id, user_id=current_user.id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this workspace.",
            )

    model_router = ModelRouter()
    decisions = await model_router.list_decisions(
        session=session,
        workspace_id=workspace_id,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    return [ModelRoutingDecisionRead.model_validate(d) for d in decisions]
