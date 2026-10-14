from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_status import DocumentStatus
from app.models.document import Document


async def create_document(
    session: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    content: str | None,
    source_type: str,
    source_name: str | None,
    mime_type: str | None,
    storage_key: str | None = None,
    workspace_id: UUID | None = None,
) -> Document:
    if workspace_id is None:
        from app.repositories.workspace import resolve_or_create_user_workspace_id

        workspace_id = await resolve_or_create_user_workspace_id(session, user_id)

    document = Document(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        content=content,
        source_type=source_type,
        source_name=source_name,
        mime_type=mime_type,
        storage_key=storage_key,
    )

    session.add(document)
    await session.commit()
    await session.refresh(document)

    return document


async def list_documents_by_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> list[Document]:
    query = select(Document).where(
        Document.user_id == user_id,
    )

    if search:
        query = query.where(
            Document.title.ilike(f"%{search}%")
        )

    if status:
        query = query.where(
            Document.status == status
        )

    if source_type:
        query = query.where(
            Document.source_type == source_type
        )

    sort_columns = {
        "created_at": Document.created_at,
        "updated_at": Document.updated_at,
        "title": Document.title,
    }

    sort_column = sort_columns[sort_by]

    if sort_order == "asc":
        order_by = (
            sort_column.asc(),
            Document.id.asc(),
        )
    else:
        order_by = (
            sort_column.desc(),
            Document.id.desc(),
        )

    result = await session.execute(
        query
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    )

    return list(result.scalars().all())


async def count_documents_by_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    search: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
) -> int:
    query = select(
        func.count(Document.id)
    ).where(
        Document.user_id == user_id,
    )

    if search:
        query = query.where(
            Document.title.ilike(f"%{search}%")
        )

    if status:
        query = query.where(
            Document.status == status
        )

    if source_type:
        query = query.where(
            Document.source_type == source_type
        )

    result = await session.execute(query)

    return result.scalar_one()


async def get_document_by_id_for_user(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> Document | None:
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )

    return result.scalar_one_or_none()

async def get_document_by_id_for_user_for_update(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> Document | None:
    """Lock document row before checking whether deletion is safe."""

    statement = (
        select(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    result = await session.execute(statement)

    return result.scalar_one_or_none()


async def update_document_status(
    session: AsyncSession,
    *,
    document: Document,
    status: str,
    error_message: str | None = None,
) -> Document:
    document.status = status
    if error_message is not None or status == DocumentStatus.READY.value:
        document.error_message = error_message

    await session.commit()
    await session.refresh(document)

    return document

async def claim_file_document_reprocessing(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> bool:
    """Atomically claim a document for reprocessing."""

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.source_type == "file",
            Document.storage_key.is_not(None),
            Document.status.in_(
                [
                    DocumentStatus.READY.value,
                    DocumentStatus.FAILED.value,
                ]
            ),
        )
        .values(
            status=DocumentStatus.PENDING.value,
            error_message=None,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)

    claimed_id = result.scalar_one_or_none()

    if claimed_id is None:
        await session.rollback()
        return False

    await session.commit()

    return True

async def claim_pending_file_processing(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> UUID | None:
    """Atomically claim a pending document and issue a fencing token."""

    run_id = uuid4()

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == DocumentStatus.PENDING.value,
        )
        .values(
            status=DocumentStatus.PROCESSING.value,
            processing_run_id=run_id,
            processing_started_at=func.now(),
            processing_heartbeat_at=func.now(),
            error_message=None,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)

    claimed_id = result.scalar_one_or_none()

    if claimed_id is None:
        await session.rollback()
        return None

    await session.commit()

    return run_id


async def mark_processing_run_failed(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    processing_run_id: UUID,
    error_message: str | None = None,
) -> bool:
    """Mark processing as failed only if the worker still owns the lease."""

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == DocumentStatus.PROCESSING.value,
            Document.processing_run_id == processing_run_id,
        )
        .values(
            status=DocumentStatus.FAILED.value,
            error_message=error_message,
            processing_run_id=None,
            processing_started_at=None,
            processing_heartbeat_at=None,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)

    if result.scalar_one_or_none() is None:
        await session.rollback()
        return False

    await session.commit()
    return True


async def heartbeat_processing_run(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    processing_run_id: UUID,
) -> bool:
    """Renew heartbeat only for the current processing lease."""

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == DocumentStatus.PROCESSING.value,
            Document.processing_run_id == processing_run_id,
        )
        .values(
            processing_heartbeat_at=func.now(),
            # Heartbeats must not change the document's
            # normal updated_at timestamp.
            updated_at=Document.updated_at,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)
    renewed = result.scalar_one_or_none() is not None

    if renewed:
        await session.commit()
    else:
        await session.rollback()

    return renewed


async def update_document_content(
    session: AsyncSession,
    *,
    document: Document,
    content: str,
) -> Document:
    document.content = content

    await session.commit()
    await session.refresh(document)

    return document


async def delete_document(
    session: AsyncSession,
    *,
    document: Document,
) -> None:
    await session.delete(document)
    await session.commit()


async def save_document(
    session: AsyncSession,
    *,
    document: Document,
) -> Document:
    await session.commit()
    await session.refresh(document)

    return document

async def refresh_processing_heartbeat(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
    processing_run_id: UUID,
) -> bool:
    """Refresh heartbeat only for the current processing lease."""

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == DocumentStatus.PROCESSING.value,
            Document.processing_run_id == processing_run_id,
        )
        .values(
            processing_heartbeat_at=func.now(),
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)

    if result.scalar_one_or_none() is None:
        await session.rollback()
        return False

    await session.commit()
    return True

async def recover_stale_file_processing(
    session: AsyncSession,
    *,
    document_id: UUID,
    user_id: UUID,
) -> bool:
    """Recover a file document whose processing lease expired."""

    # Use the PostgreSQL clock to avoid application clock skew.
    cutoff = func.now() - text("INTERVAL '5 minutes'")

    statement = (
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.source_type == "file",
            Document.status == DocumentStatus.PROCESSING.value,
            or_(
                Document.processing_heartbeat_at < cutoff,
                and_(
                    Document.processing_heartbeat_at.is_(None),
                    or_(
                        Document.processing_started_at.is_(None),
                        Document.processing_started_at < cutoff,
                    ),
                ),
            ),
        )
        .values(
            status=DocumentStatus.FAILED.value,
            processing_run_id=None,
            processing_started_at=None,
            processing_heartbeat_at=None,
        )
        .returning(Document.id)
        .execution_options(synchronize_session=False)
    )

    result = await session.execute(statement)

    if result.scalar_one_or_none() is None:
        await session.rollback()
        return False

    await session.commit()
    return True