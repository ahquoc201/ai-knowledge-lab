
"""Run retrieval evaluation against a golden dataset."""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.evaluation.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)
from app.evaluation.models import (
    EvaluationReport,
    GoldenDataset,
    QueryEvaluationResult,
)


class ChunkRetriever(Protocol):
    """Contract for retrieving ranked chunk IDs."""

    async def __call__(
        self,
        query: str,
        limit: int,
    ) -> Sequence[UUID]:
        """Return chunk IDs ordered by relevance."""
        ...


async def run_retrieval_evaluation(
    *,
    dataset: GoldenDataset,
    retriever: ChunkRetriever,
    k: int = 5,
) -> EvaluationReport:
    """Evaluate a retriever across all golden questions."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")

    results: list[QueryEvaluationResult] = []

    for case in dataset.cases:
        # The retriever is injected, not hard-coded.
        retrieved_ids = await retriever(
            case.query,
            k,
        )

        # Keep only the requested top-k results.
        ranked_ids = tuple(retrieved_ids[:k])

        precision = precision_at_k(
            ranked_ids,
            case.relevant_chunk_ids,
            k,
        )

        recall = recall_at_k(
            ranked_ids,
            case.relevant_chunk_ids,
            k,
        )

        reciprocal_rank = reciprocal_rank_at_k(
            ranked_ids,
            case.relevant_chunk_ids,
            k,
        )

        results.append(
            QueryEvaluationResult(
                case_id=case.case_id,
                query=case.query,
                ranked_chunk_ids=ranked_ids,
                relevant_chunk_ids=case.relevant_chunk_ids,
                precision_at_k=precision,
                recall_at_k=recall,
                reciprocal_rank_at_k=reciprocal_rank,
            )
        )

    count = len(results)

    mean_precision = (
        sum(result.precision_at_k for result in results)
        / count
    )

    mean_recall = (
        sum(result.recall_at_k for result in results)
        / count
    )

    mrr = mean_reciprocal_rank(
        [result.reciprocal_rank_at_k for result in results]
    )

    return EvaluationReport(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        k=k,
        results=tuple(results),
        mean_precision_at_k=mean_precision,
        mean_recall_at_k=mean_recall,
        mrr_at_k=mrr,
    )
