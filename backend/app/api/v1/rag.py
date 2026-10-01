from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
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
    result = await answer_with_rag(
        session,
        user_id=current_user.id,
        query=payload.query,
        llm=llm,
        limit=payload.limit,
    )

    return RAGResponse(
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