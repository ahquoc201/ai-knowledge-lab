
"""Data models for retrieval evaluation."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    """A question with its known relevant chunks."""

    case_id: str
    query: str
    relevant_chunk_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")

        if not self.query.strip():
            raise ValueError("query must not be empty")

        relevant_ids = frozenset(self.relevant_chunk_ids)

        if not relevant_ids:
            raise ValueError(
                "relevant_chunk_ids must not be empty"
            )

        object.__setattr__(
            self,
            "relevant_chunk_ids",
            relevant_ids,
        )


@dataclass(frozen=True, slots=True)
class GoldenDataset:
    """A versioned collection of evaluation questions."""

    dataset_id: str
    version: str
    cases: tuple[GoldenQuery, ...]

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")

        if not self.version.strip():
            raise ValueError("version must not be empty")

        cases = tuple(self.cases)

        if not cases:
            raise ValueError("cases must not be empty")

        case_ids = [case.case_id for case in cases]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Duplicate evaluation case IDs")

        object.__setattr__(self, "cases", cases)


@dataclass(frozen=True, slots=True)
class QueryEvaluationResult:
    """Retrieval scores for a single evaluation question."""

    case_id: str
    query: str
    ranked_chunk_ids: tuple[UUID, ...]
    relevant_chunk_ids: frozenset[UUID]

    precision_at_k: float
    recall_at_k: float
    reciprocal_rank_at_k: float


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Aggregated retrieval evaluation results."""

    dataset_id: str
    dataset_version: str
    k: int

    results: tuple[QueryEvaluationResult, ...]

    mean_precision_at_k: float
    mean_recall_at_k: float
    mrr_at_k: float
