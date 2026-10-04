import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.repositories.document import get_document_by_id_for_user
from app.services.file_storage import delete_upload_file
from app.services.ingestion import process_document


async def _process_document_task(
    *,
    document_id: UUID,
    user_id: UUID,
    file_path: Path,
) -> None:
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_factory() as session:
            document = await get_document_by_id_for_user(
                session,
                document_id=document_id,
                user_id=user_id,
            )

            if document is None:
                raise ValueError(
                    f"Document not found: {document_id}"
                )

            data = file_path.read_bytes()

            await process_document(
                session,
                document=document,
                data=data,
            )
    finally:
        await engine.dispose()


@celery_app.task(
    name="documents.process",
)
def process_document_task(
    document_id: str,
    user_id: str,
    file_path: str,
) -> None:
    path = Path(file_path)

    try:
        asyncio.run(
            _process_document_task(
                document_id=UUID(document_id),
                user_id=UUID(user_id),
                file_path=path,
            )
        )
    finally:
        delete_upload_file(path)