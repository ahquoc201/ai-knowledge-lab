from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_permission
from app.core.config import get_settings
from app.core.message_role import MessageRole
from app.core.workspace_role import AuditOutcome, WorkspacePermission
from app.db.session import get_session
from app.llm.ollama import (
    OllamaLLMProvider,
    get_ollama_llm_provider,
)
from app.models.user import User
from app.models.workspace_membership import WorkspaceMembership
from app.schemas.rag import (
    RAGRequest,
    RAGResponse,
    RAGSourceResponse,
)
from app.services.audit import record_audit_event
from app.services.chat_history import get_workspace_conversation_history
from app.services.conversation import (
    create_user_conversation,
    get_workspace_conversation,
)
from app.services.message import create_workspace_conversation_message
from app.services.message_source import save_assistant_message_sources
from app.services.rag import answer_with_rag
from app.services.rag_stream import answer_with_rag_stream
from app.services.rate_limiter import get_rate_limiter

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
)


@router.post(
    "/ask",
    response_model=RAGResponse,
)
async def ask_rag(
    payload: RAGRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_CREATE)),
    ],
    llm: Annotated[
        OllamaLLMProvider,
        Depends(get_ollama_llm_provider),
    ],
) -> RAGResponse:
    settings = get_settings()
    limiter = get_rate_limiter()
    limiter.enforce(str(current_user.id), settings.rate_limit_rag_per_user_per_minute, 60, "rag_chat_user")
    limiter.enforce(str(membership.workspace_id), settings.rate_limit_rag_per_workspace_per_minute, 60, "rag_chat_workspace")

    if payload.conversation_id is None:
        title = payload.query.strip()[:255] or None

        conversation = await create_user_conversation(
            session,
            user=current_user,
            title=title,
            workspace_id=membership.workspace_id,
        )

        conversation_id = conversation.id
        history = []
    else:
        conversation_id = payload.conversation_id

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

        history = await get_workspace_conversation_history(
            session,
            workspace_id=membership.workspace_id,
            conversation_id=conversation_id,
        )

        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    user_message = await create_workspace_conversation_message(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=payload.query,
    )

    if user_message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    result = await answer_with_rag(
        session,
        user_id=current_user.id,
        workspace_id=membership.workspace_id,
        query=payload.query,
        llm=llm,
        limit=payload.limit,
        history=history,
    )

    assistant_message = await create_workspace_conversation_message(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=result.answer,
    )

    if assistant_message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await save_assistant_message_sources(
        session,
        message=assistant_message,
        sources=result.sources,
    )

    await record_audit_event(
        session,
        workspace_id=membership.workspace_id,
        action="chat.ask",
        resource_type="conversation",
        actor_id=current_user.id,
        resource_id=conversation_id,
        outcome=AuditOutcome.SUCCESS,
        details={"source_count": len(result.sources)},
    )

    return RAGResponse(
        conversation_id=conversation_id,
        answer=result.answer,
        sources=[
            RAGSourceResponse(
                source_index=source.source_index,
                document_id=source.document_id,
                chunk_id=source.chunk_id,
                chunk_index=source.chunk_index,
                content=source.content,
                similarity=source.similarity,
                document_title=source.document_title,
                char_start=source.char_start,
                char_end=source.char_end,
            )
            for source in result.sources
        ],
    )


@router.post(
    "/ask/stream",
)
async def ask_rag_stream(
    payload: RAGRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[
        WorkspaceMembership,
        Depends(require_workspace_permission(WorkspacePermission.CHAT_CREATE)),
    ],
    llm: Annotated[
        OllamaLLMProvider,
        Depends(get_ollama_llm_provider),
    ],
) -> StreamingResponse:
    settings = get_settings()
    limiter = get_rate_limiter()
    limiter.enforce(str(current_user.id), settings.rate_limit_rag_per_user_per_minute, 60, "rag_chat_user")
    limiter.enforce(str(membership.workspace_id), settings.rate_limit_rag_per_workspace_per_minute, 60, "rag_chat_workspace")

    if payload.conversation_id is None:
        title = payload.query.strip()[:255] or None

        conversation = await create_user_conversation(
            session,
            user=current_user,
            title=title,
            workspace_id=membership.workspace_id,
        )

        conversation_id = conversation.id
        history = []
    else:
        conversation_id = payload.conversation_id

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

        history = await get_workspace_conversation_history(
            session,
            workspace_id=membership.workspace_id,
            conversation_id=conversation_id,
        )

        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    user_message = await create_workspace_conversation_message(
        session,
        workspace_id=membership.workspace_id,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=payload.query,
    )

    if user_message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await record_audit_event(
        session,
        workspace_id=membership.workspace_id,
        action="chat.ask_stream",
        resource_type="conversation",
        actor_id=current_user.id,
        resource_id=conversation_id,
        outcome=AuditOutcome.SUCCESS,
    )

    stream_generator = answer_with_rag_stream(
        session,
        user=current_user,
        conversation_id=conversation_id,
        workspace_id=membership.workspace_id,
        query=payload.query,
        llm=llm,
        limit=payload.limit,
        history=history,
    )

    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": str(conversation_id),
        },
    )