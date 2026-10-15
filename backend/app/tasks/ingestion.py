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
from app.services.file_extractor import (
    FileExtractionError,
    UnsupportedFileTypeError,
)
from app.services.file_storage import read_stored_file
from app.services.ingestion import process_document
from app.services.processing_heartbeat import (
    maintain_processing_heartbeat,
)

logger = logging.getLogger(__name__)


class DocumentNotFoundError(ValueError):
    """Raised when a document cannot be found in the database."""


async def _process_document_task(
    *,
    document_id: UUID,
    user_id: UUID,
    expected_workspace_id: UUID | None = None,
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

            # Defensive visibility check: if not found immediately, retry a brief read
            # after a short delay in case of transaction commit propagation lag.
            if document is None:
                await asyncio.sleep(0.5)
                document = await get_document_by_id_for_user(
                    session,
                    document_id=document_id,
                    user_id=user_id,
                )

            if document is None:
                raise DocumentNotFoundError(
                    f"Document not found: {document_id}"
                )

            if expected_workspace_id is not None and document.workspace_id != expected_workspace_id:
                raise ValueError(
                    f"Workspace mismatch: document {document_id} belongs to workspace {document.workspace_id}, "
                    f"expected {expected_workspace_id}. Cross-tenant ingestion attempt blocked."
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
    expected_workspace_id: str | None = None,
) -> None:
    task_id = getattr(getattr(self, "request", None), "id", "local")
    is_direct_call = getattr(getattr(self, "request", None), "called_directly", False)

    task_kwargs = {
        "document_id": UUID(document_id),
        "user_id": UUID(user_id),
    }
    if expected_workspace_id is not None:
        task_kwargs["expected_workspace_id"] = UUID(expected_workspace_id)

    try:
        asyncio.run(
            _process_document_task(**task_kwargs)
        )
    except DocumentNotFoundError:
        # Document was deleted or rolled back before processing began.
        # Discard the task without retrying to prevent log storms.
        logger.warning(
            "Task %s: Document %s (user: %s) not found in database. Discarding task without retrying.",
            task_id,
            document_id,
            user_id,
        )
        if is_direct_call:
            raise
        return
    except (UnsupportedFileTypeError, FileExtractionError, ValueError) as exc:
        # Permanent extraction/input errors: Document has already been marked FAILED in DB.
        # Do not retry permanent errors.
        logger.warning(
            "Task %s: Permanent failure processing document %s: %s. Document marked failed in database.",
            task_id,
            document_id,
            exc,
        )
        if is_direct_call:
            raise
        return
    except Exception as exc:
        # Transient errors (e.g. database connectivity loss, network glitch)
        retries = getattr(getattr(self, "request", None), "retries", 0)
        max_retries = getattr(self, "max_retries", 3)
        default_delay = getattr(self, "default_retry_delay", 5)

        if hasattr(self, "retry") and retries < max_retries and not is_direct_call:
            countdown = default_delay * (2 ** retries)
            logger.warning(
                "Task %s: Transient error processing document %s: %s. Retrying in %ss (attempt %s/%s)...",
                task_id,
                document_id,
                exc,
                countdown,
                retries + 1,
                max_retries,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc

        logger.exception(
            "Task %s: Document processing task failed permanently after %s retries for document %s",
            task_id,
            max_retries,
            document_id,
        )
        raise
