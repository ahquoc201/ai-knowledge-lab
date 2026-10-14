import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.document_status import DocumentStatus
from app.db.session import get_session
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from app.services.document import (
    DocumentProcessingError,
    InvalidDocumentUpdateError,
    UnsupportedDocumentContentUpdateError,
    claim_user_file_reprocessing,
    create_user_document,
    delete_user_document,
    get_user_document,
    list_user_documents,
    recover_user_stale_file_processing,
    set_document_status,
    update_user_document,
)
from app.services.file_extractor import (
    UnsupportedFileTypeError,
    validate_supported_file_type,
)
from app.services.file_storage import (
    delete_upload_file,
    save_upload_file,
)
from app.services.reprocessing import (
    EmptyDocumentContentError,
    UnsupportedDocumentReprocessingError,
    reprocess_text_document,
)
from app.tasks.ingestion import process_document_task

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    data: DocumentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    document = await create_user_document(
        session,
        user=current_user,
        data=data,
    )

    try:
        process_document_task.delay(
            str(document.id),
            str(current_user.id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to enqueue ingestion task for document %s: %s",
            document.id,
            exc,
        )
        await set_document_status(
            session,
            document=document,
            status=DocumentStatus.FAILED,
            error_message="Failed to schedule background processing task",
        )

    return DocumentResponse.model_validate(document)

@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
) -> DocumentResponse:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename",
        )

    try:
        validate_supported_file_type(file.filename)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc

    data = await file.read(settings.max_upload_size_bytes + 1)

    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded file exceeds the maximum allowed size",
        )

    stored_path = save_upload_file(
        filename=file.filename,
        data=data,
    )

    document = None

    try:
        document = await create_user_document(
            session,
            user=current_user,
            data=DocumentCreate(
                title=file.filename,
                content=None,
                source_type="file",
                source_name=file.filename,
                mime_type=file.content_type,
            ),
            storage_key=stored_path.name,
        )

        process_document_task.delay(
            str(document.id),
            str(current_user.id),
        )

    except Exception:
        if document is None:
            delete_upload_file(stored_path)
        else:
            await set_document_status(
                session,
                document=document,
                status=DocumentStatus.FAILED,
                error_message="Failed to schedule background processing task",
            )

        raise

    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=DocumentListResponse,
)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: Annotated[
        str | None,
        Query(min_length=1, max_length=255),
    ] = None,
    document_status: Annotated[
        str | None,
        Query(alias="status", max_length=30),
    ] = None,
    source_type: Annotated[
        str | None,
        Query(max_length=50),
    ] = None,
    sort_by: Annotated[
        Literal["created_at", "updated_at", "title"],
        Query(),
    ] = "created_at",
    sort_order: Annotated[
        Literal["asc", "desc"],
        Query(),
    ] = "desc",
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 20,
    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
) -> DocumentListResponse:
    documents, total = await list_user_documents(
        session,
        user=current_user,
        search=search,
        status=document_status,
        source_type=source_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    return DocumentListResponse(
        items=[
            DocumentResponse.model_validate(document)
            for document in documents
        ],
        total=total,
        limit=limit,
        offset=offset,
    )

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def get_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    document = await get_user_document(
        session,
        user=current_user,
        document_id=document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse.model_validate(document)

@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def update_document(
    document_id: UUID,
    data: DocumentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    try:
        document = await update_user_document(
            session,
            user=current_user,
            document_id=document_id,
            data=data,
        )
    except UnsupportedDocumentContentUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InvalidDocumentUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse.model_validate(document)

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    try:
        deleted = await delete_user_document(
            session,
            user=current_user,
            document_id=document_id,
        )

    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentResponse,
    responses={
        202: {"description": "File reprocessing queued"},
    },
)
async def reprocess_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> DocumentResponse:
    document = await get_user_document(
        session,
        user=current_user,
        document_id=document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.source_type == "file":
        if not document.storage_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document has no stored source file",
            )

        if document.status == DocumentStatus.PROCESSING.value:
            await recover_user_stale_file_processing(
                session,
                user=current_user,
                document_id=document.id,
            )

            # Reload status after the conditional UPDATE.
            # Recovery may succeed, fail, or another worker
            # may finish processing concurrently.
            await session.refresh(document)

        if document.status in {
            DocumentStatus.PENDING.value,
            DocumentStatus.PROCESSING.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is already queued or processing",
            )

        claimed = await claim_user_file_reprocessing(
            session,
            user=current_user,
            document_id=document.id,
        )

        if not claimed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document is already queued or processing",
            )

        await session.refresh(document)

        try:
            process_document_task.delay(
                str(document.id),
                str(current_user.id),
            )
        except Exception as exc:
            await set_document_status(
                session,
                document=document,
                status=DocumentStatus.FAILED,
                error_message="Unable to schedule document reprocessing",
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to schedule document reprocessing",
            ) from exc

        response.status_code = status.HTTP_202_ACCEPTED
        return DocumentResponse.model_validate(document)

    try:
        document = await reprocess_text_document(
            session,
            document=document,
        )
    except UnsupportedDocumentReprocessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except EmptyDocumentContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return DocumentResponse.model_validate(document)
