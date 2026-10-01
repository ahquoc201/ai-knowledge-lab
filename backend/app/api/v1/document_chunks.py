from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.repositories.document_chunk import list_document_chunks
from app.schemas.document_chunk import (
    DocumentChunkCreateRequest,
    DocumentChunkResponse,
)
from app.services.document import get_user_document
from app.services.document_chunk import (
    chunk_document,
    embed_document_chunks,
)

router = APIRouter(
    prefix="/documents",
    tags=["document-chunks"],
)


@router.post(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkResponse],
)
async def create_document_chunks(
    document_id: UUID,
    payload: DocumentChunkCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[DocumentChunkResponse]:
    document = await get_user_document(
        session,
        document_id=document_id,
        user=current_user,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    chunks = await chunk_document(
        session,
        document=document,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
    )

    return chunks


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkResponse],
)
async def get_document_chunks(
    document_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[DocumentChunkResponse]:
    document = await get_user_document(
        session,
        document_id=document_id,
        user=current_user,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    chunks = await list_document_chunks(
        session,
        document_id=document.id,
    )

    return chunks

@router.post(
    "/{document_id}/embeddings",
    status_code=status.HTTP_200_OK,
)
async def create_document_embeddings(
    document_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, int | str]:
    document = await get_user_document(
        session,
        document_id=document_id,
        user=current_user,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    chunks = await embed_document_chunks(
        session,
        document_id=document.id,
    )

    return {
        "document_id": str(document.id),
        "embedded_chunks": len(chunks),
    }