from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_permission
from app.core.workspace_role import AuditOutcome, WorkspacePermission
from app.db.session import get_session
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageResponse
from app.schemas.message_source import MessageSourceResponse
from app.services.audit import record_audit_event
from app.services.conversation import (
    create_user_conversation,
    delete_workspace_conversation,
    get_workspace_conversation,
    list_workspace_conversations,
    update_workspace_conversation,
)
from app.services.message import list_workspace_conversation_messages
from app.services.message_source import (
    get_message_sources_by_message_ids,
)

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    data: ConversationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_CREATE)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationResponse:
    conversation = await create_user_conversation(
        session,
        user=current_user,
        title=data.title,
        workspace_id=membership.workspace_id,
    )

    await record_audit_event(
        session,
        workspace_id=membership.workspace_id,
        action="conversation.create",
        resource_type="conversation",
        actor_id=current_user.id,
        resource_id=conversation.id,
        outcome=AuditOutcome.SUCCESS,
    )

    return ConversationResponse.model_validate(conversation)


@router.get(
    "",
    response_model=list[ConversationResponse],
)
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ConversationResponse]:
    conversations = await list_workspace_conversations(
        session,
        workspace_id=membership.workspace_id,
    )

    return [
        ConversationResponse.model_validate(conversation)
        for conversation in conversations
    ]


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_READ)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationDetailResponse:
    conversation = await get_workspace_conversation(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = await list_workspace_conversation_messages(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation.id,
    )

    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    sources_by_message_id = await get_message_sources_by_message_ids(
        session,
        message_ids=[
            message.id
            for message in messages
        ],
    )

    return ConversationDetailResponse(
        **ConversationResponse.model_validate(
            conversation
        ).model_dump(),
        messages=[
            MessageResponse.model_validate(message).model_copy(
                update={
                    "sources": [
                        MessageSourceResponse.model_validate(source)
                        for source in sources_by_message_id[message.id]
                    ],
                }
            )
            for message in messages
        ],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
async def update_conversation(
    conversation_id: UUID,
    data: ConversationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_CREATE)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationResponse:
    conversation = await update_workspace_conversation(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
        title=data.title,
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await record_audit_event(
        session,
        workspace_id=membership.workspace_id,
        action="conversation.update",
        resource_type="conversation",
        actor_id=current_user.id,
        resource_id=conversation.id,
        outcome=AuditOutcome.SUCCESS,
    )

    return ConversationResponse.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_CREATE)),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    deleted = await delete_workspace_conversation(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await record_audit_event(
        session,
        workspace_id=membership.workspace_id,
        action="conversation.delete",
        resource_type="conversation",
        actor_id=current_user.id,
        resource_id=conversation_id,
        outcome=AuditOutcome.SUCCESS,
    )