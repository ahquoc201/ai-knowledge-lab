from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.message_role import MessageRole
from app.db.session import get_session
from app.llm.ollama import (
    OllamaLLMProvider,
    get_ollama_llm_provider,
)
from app.models.user import User
from app.schemas.rag import (
    RAGRequest,
    RAGResponse,
    RAGSourceResponse,
)
from app.services.chat_history import get_conversation_history
from app.services.conversation import create_user_conversation
from app.services.message import create_conversation_message
from app.services.message_source import save_assistant_message_sources
from app.services.rag import answer_with_rag

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
    llm: Annotated[
        OllamaLLMProvider,
        Depends(get_ollama_llm_provider),
    ],
) -> RAGResponse:
    if payload.conversation_id is None:
        title = payload.query.strip()[:255] or None

        conversation = await create_user_conversation(
            session,
            user=current_user,
            title=title,
        )

        conversation_id = conversation.id
        history = []
    else:
        conversation_id = payload.conversation_id

        history = await get_conversation_history(
            session,
            user=current_user,
            conversation_id=conversation_id,
        )

        if history is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    user_message = await create_conversation_message(
        session,
        user=current_user,
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
        query=payload.query,
        llm=llm,
        limit=payload.limit,
        history=history,
    )

    assistant_message = await create_conversation_message(
        session,
        user=current_user,
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
            )
            for source in result.sources
        ],
    )