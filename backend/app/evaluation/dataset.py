
"""Load and validate retrieval golden datasets."""

import json
from pathlib import Path
from uuid import UUID

from app.evaluation.models import GoldenDataset, GoldenQuery


def _require_string(
    data: dict,
    field: str,
    *,
    context: str,
) -> str:
    """Extract a required non-empty string field."""

    value = data.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{context}.{field} must be a non-empty string"
        )

    return value


def _parse_relevant_chunk_ids(
    value: object,
    *,
    context: str,
) -> frozenset[UUID]:
    """Parse and validate relevant chunk UUIDs."""

    if not isinstance(value, list) or not value:
        raise ValueError(
            f"{context}.relevant_chunk_ids "
            "must be a non-empty list"
        )

    parsed_ids: list[UUID] = []

    for index, raw_id in enumerate(value):
        if not isinstance(raw_id, str):
            raise TypeError(
                f"{context}.relevant_chunk_ids[{index}] "
                "must be a UUID string"
            )

        try:
            chunk_id = UUID(raw_id)
        except ValueError as exc:
            raise ValueError(
                f"{context}.relevant_chunk_ids[{index}] "
                "contains an invalid UUID"
            ) from exc

        parsed_ids.append(chunk_id)

    if len(parsed_ids) != len(set(parsed_ids)):
        raise ValueError(
            f"{context}.relevant_chunk_ids "
            "contains duplicate UUIDs"
        )

    return frozenset(parsed_ids)


def load_golden_dataset(
    path: str | Path,
) -> GoldenDataset:
    """Load a golden dataset from a UTF-8 JSON file."""

    file_path = Path(path)

    try:
        payload = json.loads(
            file_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid golden dataset JSON: {file_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise TypeError(
            "Golden dataset root must be a JSON object"
        )

    dataset_id = _require_string(
        payload,
        "dataset_id",
        context="dataset",
    )

    version = _require_string(
        payload,
        "version",
        context="dataset",
    )

    raw_cases = payload.get("cases")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(
            "dataset.cases must be a non-empty list"
        )

    cases: list[GoldenQuery] = []

    for index, raw_case in enumerate(raw_cases):
        context = f"dataset.cases[{index}]"

        if not isinstance(raw_case, dict):
            raise TypeError(
                f"{context} must be a JSON object"
            )

        case_id = _require_string(
            raw_case,
            "case_id",
            context=context,
        )

        query = _require_string(
            raw_case,
            "query",
            context=context,
        )

        relevant_ids = _parse_relevant_chunk_ids(
            raw_case.get("relevant_chunk_ids"),
            context=context,
        )

        cases.append(
            GoldenQuery(
                case_id=case_id,
                query=query,
                relevant_chunk_ids=relevant_ids,
            )
        )

    return GoldenDataset(
        dataset_id=dataset_id,
        version=version,
        cases=tuple(cases),
    )
