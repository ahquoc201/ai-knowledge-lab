
"""Validate golden dataset references against PostgreSQL."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.models import GoldenDataset
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class GoldenDatasetReferenceError(ValueError):
    """Golden dataset contains missing or inaccessible chunks."""

    def __init__(
        self,
        missing_chunk_ids: frozenset[UUID],
    ) -> None:
        self.missing_chunk_ids = missing_chunk_ids

        formatted_ids = ", ".join(
            str(chunk_id)
            for chunk_id in sorted(missing_chunk_ids)
        )

        super().__init__(
            "Golden dataset contains missing or inaccessible "
            f"chunk IDs: {formatted_ids}"
        )


async def validate_golden_dataset_references(
    session: AsyncSession,
    *,
    dataset: GoldenDataset,
    user_id: UUID,
) -> None:
    """Ensure all relevant chunks exist and belong to the user."""

    # Collect unique relevant IDs across all evaluation cases.
    expected_ids = {
        chunk_id
        for case in dataset.cases
        for chunk_id in case.relevant_chunk_ids
    }

    # Query only chunks owned by the evaluation user.
    statement = (
        select(DocumentChunk.id)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            Document.user_id == user_id,
            DocumentChunk.id.in_(expected_ids),
        )
    )

    result = await session.scalars(statement)

    existing_ids = set(result.all())

    missing_ids = expected_ids - existing_ids

    if missing_ids:
        raise GoldenDatasetReferenceError(
            missing_chunk_ids=frozenset(missing_ids),
        )
