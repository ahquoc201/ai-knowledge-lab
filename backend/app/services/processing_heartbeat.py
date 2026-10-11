
import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.repositories.document import refresh_processing_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15.0


async def maintain_processing_heartbeat(
    *,
    document_id: UUID,
    user_id: UUID,
    processing_run_id: UUID,
    stop_event: asyncio.Event,
    interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    """Refresh the processing lease until stopped or ownership is lost."""

    if interval_seconds <= 0:
        raise ValueError("Heartbeat interval must be positive")

    settings = get_settings()

    # Independent engine and sessions for heartbeat updates.
    # Never share the ingestion session across concurrent tasks.
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
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval_seconds,
                )
                break
            except TimeoutError:
                pass

            if stop_event.is_set():
                break

            try:
                async with session_factory() as session:
                    renewed = await refresh_processing_heartbeat(
                        session,
                        document_id=document_id,
                        user_id=user_id,
                        processing_run_id=processing_run_id,
                    )

            except Exception:
                # A transient DB error should not silently
                # terminate heartbeat monitoring.
                logger.exception(
                    "Failed to refresh processing heartbeat "
                    "for document %s",
                    document_id,
                )
                continue

            if not renewed:
                # Another worker may own this document now.
                # The final DB write is still protected by
                # the fencing-token check.
                logger.warning(
                    "Processing lease lost for document %s, run %s",
                    document_id,
                    processing_run_id,
                )
                return

    finally:
        await engine.dispose()
