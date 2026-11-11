from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.search import (
    HybridSearchRequest,
    HybridSearchResultResponse,
    SemanticSearchRequest,
    SemanticSearchResultResponse,
)
from app.services.retrieval import hybrid_search
from app.services.semantic_search import semantic_search

router = APIRouter(
    prefix="/search",
    tags=["search"],
)


@router.post(
    "/semantic",
    response_model=list[SemanticSearchResultResponse],
)
async def search_semantic(
    payload: SemanticSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[SemanticSearchResultResponse]:
    results = await semantic_search(
        session,
        user_id=current_user.id,
        query=payload.query,
        limit=payload.limit,
    )

    return [
        SemanticSearchResultResponse(
            document_id=result.chunk.document_id,
            chunk_id=result.chunk.id,
            chunk_index=result.chunk.chunk_index,
            content=result.chunk.content,
            similarity=result.similarity,
        )
        for result in results
    ]


@router.post(
    "/hybrid",
    response_model=list[HybridSearchResultResponse],
)
async def search_hybrid(
    payload: HybridSearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[HybridSearchResultResponse]:
    results = await hybrid_search(
        session,
        user_id=current_user.id,
        workspace_id=payload.workspace_id,
        query=payload.query,
        limit=payload.limit,
        rrf_k=payload.rrf_k,
    )

    return [
        HybridSearchResultResponse(
            document_id=result.chunk.document_id,
            chunk_id=result.chunk.id,
            chunk_index=result.chunk.chunk_index,
            content=result.chunk.content,
            rrf_score=result.rrf_score,
            dense_rank=result.dense_rank,
            keyword_rank=result.keyword_rank,
            dense_similarity=result.dense_similarity,
            keyword_score=result.keyword_score,
            provenance=result.provenance.value,
            document_title=result.document_title,
        )
        for result in results
    ]
