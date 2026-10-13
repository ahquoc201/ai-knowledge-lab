
import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.repositories.document import (
    claim_pending_file_processing,
    get_document_by_id_for_user,
    mark_processing_run_failed,
)
from app.services.file_storage import read_stored_file
from app.services.ingestion import process_document
from app.services.processing_heartbeat import (
    maintain_processing_heartbeat,
)

logger = logging.getLogger(__name__)


async def _process_document_task(
    *,
    document_id: UUID,
    user_id: UUID,
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

            processing_run_id = await claim_pending_file_processing(
                session,
                document_id=document_id,
                user_id=user_id,
            )

            # Ignore duplicate or outdated jobs.
            if processing_run_id is None:
                return

            # Start a heartbeat task with its own DB connection.
            stop_event = asyncio.Event()

            heartbeat_task = asyncio.create_task(
                maintain_processing_heartbeat(
                    document_id=document_id,
                    user_id=user_id,
                    processing_run_id=processing_run_id,
                    stop_event=stop_event,
                )
            )

            try:
                try:
                    await session.refresh(document)

                    source_type = getattr(document, "source_type", "file")
                    if source_type == "text":
                        content = getattr(document, "content", None)
                        if not content or not content.strip():
                            raise ValueError("Document content is empty")
                        data = content.encode("utf-8")
                    else:
                        if not getattr(document, "storage_key", None):
                            raise ValueError(
                                "Document has no stored source file"
                            )

                        # Read from disk without blocking the
                        # event loop used by the heartbeat.
                        data = await asyncio.to_thread(
                            read_stored_file,
                            document.storage_key,
                        )

                except Exception as exc:
                    await session.rollback()

                    # Only this run may record the failure.
                    await mark_processing_run_failed(
                        session,
                        document_id=document_id,
                        user_id=user_id,
                        processing_run_id=processing_run_id,
                        error_message=str(exc),
                    )

                    raise

                # This service handles processing errors
                # and validates the fencing token at commit.
                await process_document(
                    session,
                    document=document,
                    data=data,
                    processing_run_id=processing_run_id,
                )

            finally:
                # Always stop the heartbeat, whether
                # processing succeeded or failed.
                stop_event.set()

                try:
                    await heartbeat_task
                except Exception:
                    logger.exception(
                        "Heartbeat task failed for document %s",
                        document_id,
                    )

    finally:
        await engine.dispose()


@celery_app.task(
    name="documents.process",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_document_task(
    self,
    document_id: str,
    user_id: str,
) -> None:
    try:
        asyncio.run(
            _process_document_task(
                document_id=UUID(document_id),
                user_id=UUID(user_id),
            )
        )
    except Exception as exc:
        logger.exception(
            "Document processing task failed for %s",
            document_id,
        )
        if hasattr(self, "request") and self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
