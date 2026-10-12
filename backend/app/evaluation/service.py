
"""Run semantic retrieval evaluation on a consistent DB snapshot."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.evaluation.adapters import SemanticSearchRetriever
from app.evaluation.dataset_validator import (
    validate_golden_dataset_references,
)
from app.evaluation.models import EvaluationReport, GoldenDataset
from app.evaluation.runner import run_retrieval_evaluation


async def evaluate_semantic_search(
    *,
    engine: AsyncEngine,
    dataset: GoldenDataset,
    user_id: UUID,
    k: int = 5,
) -> EvaluationReport:
    """Evaluate retrieval using one read-only PostgreSQL snapshot."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")

    # Use a dedicated connection for the evaluation run.
    async with engine.connect() as connection:
        # Must be configured before beginning the transaction.
        await connection.execution_options(
            isolation_level="REPEATABLE READ",
        )

        async with connection.begin():
            # Evaluation must never modify production data.
            await connection.execute(
                text("SET TRANSACTION READ ONLY")
            )

            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
            ) as session:
                # Fail fast if golden labels do not exist
                # or are inaccessible to this user.
                await validate_golden_dataset_references(
                    session,
                    dataset=dataset,
                    user_id=user_id,
                )

                # Adapter retains the same session and user scope.
                retriever = SemanticSearchRetriever(
                    session,
                    user_id=user_id,
                )

                # All retrieval queries use the same DB snapshot.
                report = await run_retrieval_evaluation(
                    dataset=dataset,
                    retriever=retriever,
                    k=k,
                )

                return report
