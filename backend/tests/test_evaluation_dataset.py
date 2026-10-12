
"""Unit tests for retrieval golden dataset loading."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from app.evaluation.dataset import load_golden_dataset

A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)


def make_valid_payload() -> dict:
    """Build a valid golden dataset JSON payload."""

    return {
        "dataset_id": "retrieval-baseline",
        "version": "1.0",
        "cases": [
            {
                "case_id": "postgresql-001",
                "query": "PostgreSQL là gì?",
                "relevant_chunk_ids": [
                    str(A),
                    str(B),
                ],
            },
            {
                "case_id": "redis-001",
                "query": "Redis dùng để làm gì?",
                "relevant_chunk_ids": [
                    str(C),
                ],
            },
        ],
    }


def write_dataset(
    tmp_path: Path,
    payload: object,
) -> Path:
    """Write a JSON payload to a temporary file."""

    path = tmp_path / "retrieval_golden.json"

    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    return path


def test_load_valid_golden_dataset(tmp_path):
    path = write_dataset(
        tmp_path,
        make_valid_payload(),
    )

    dataset = load_golden_dataset(path)

    assert dataset.dataset_id == "retrieval-baseline"
    assert dataset.version == "1.0"
    assert len(dataset.cases) == 2

    first, second = dataset.cases

    assert first.case_id == "postgresql-001"
    assert first.query == "PostgreSQL là gì?"
    assert first.relevant_chunk_ids == frozenset({A, B})

    assert second.case_id == "redis-001"
    assert second.query == "Redis dùng để làm gì?"
    assert second.relevant_chunk_ids == frozenset({C})


def test_loader_preserves_case_order(tmp_path):
    path = write_dataset(
        tmp_path,
        make_valid_payload(),
    )

    dataset = load_golden_dataset(path)

    assert [case.case_id for case in dataset.cases] == [
        "postgresql-001",
        "redis-001",
    ]


def test_loader_accepts_string_path(tmp_path):
    path = write_dataset(
        tmp_path,
        make_valid_payload(),
    )

    dataset = load_golden_dataset(str(path))

    assert dataset.dataset_id == "retrieval-baseline"


def test_invalid_json_rejected(tmp_path):
    path = tmp_path / "invalid.json"

    path.write_text(
        '{"dataset_id": ',
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Invalid golden dataset JSON",
    ):
        load_golden_dataset(path)


def test_missing_file_raises_file_not_found(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "invalid",
        123,
    ],
)
def test_root_must_be_json_object(tmp_path, payload):
    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        TypeError,
        match="Golden dataset root must be a JSON object",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", ""),
        ("dataset_id", "   "),
        ("dataset_id", None),
        ("dataset_id", 123),
        ("version", ""),
        ("version", "   "),
        ("version", None),
        ("version", 123),
    ],
)
def test_required_dataset_strings_rejected(
    tmp_path,
    field,
    value,
):
    payload = make_valid_payload()
    payload[field] = value

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match=f"dataset.{field} must be a non-empty string",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "field",
    [
        "dataset_id",
        "version",
    ],
)
def test_missing_dataset_field_rejected(tmp_path, field):
    payload = make_valid_payload()
    del payload[field]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match=f"dataset.{field} must be a non-empty string",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "cases",
    [
        [],
        None,
        {},
        "invalid",
    ],
)
def test_invalid_cases_collection_rejected(
    tmp_path,
    cases,
):
    payload = make_valid_payload()
    payload["cases"] = cases

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="dataset.cases must be a non-empty list",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "invalid_case",
    [
        None,
        123,
        "invalid",
        [],
    ],
)
def test_case_must_be_object(
    tmp_path,
    invalid_case,
):
    payload = make_valid_payload()
    payload["cases"] = [invalid_case]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        TypeError,
        match=r"dataset.cases\[0\] must be a JSON object",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_id", ""),
        ("case_id", "   "),
        ("case_id", None),
        ("case_id", 123),
        ("query", ""),
        ("query", "   "),
        ("query", None),
        ("query", 123),
    ],
)
def test_invalid_case_strings_rejected(
    tmp_path,
    field,
    value,
):
    payload = make_valid_payload()
    payload["cases"][0][field] = value

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match=f"{field} must be a non-empty string",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "relevant_ids",
    [
        [],
        None,
        {},
        "invalid",
    ],
)
def test_invalid_relevant_ids_collection_rejected(
    tmp_path,
    relevant_ids,
):
    payload = make_valid_payload()

    payload["cases"][0]["relevant_chunk_ids"] = relevant_ids

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="must be a non-empty list",
    ):
        load_golden_dataset(path)


@pytest.mark.parametrize(
    "invalid_id",
    [
        None,
        123,
        {"id": "invalid"},
    ],
)
def test_non_string_uuid_rejected(
    tmp_path,
    invalid_id,
):
    payload = make_valid_payload()

    payload["cases"][0]["relevant_chunk_ids"] = [
        invalid_id,
    ]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        TypeError,
        match="must be a UUID string",
    ):
        load_golden_dataset(path)


def test_invalid_uuid_string_rejected(tmp_path):
    payload = make_valid_payload()

    payload["cases"][0]["relevant_chunk_ids"] = [
        "not-a-valid-uuid",
    ]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="contains an invalid UUID",
    ):
        load_golden_dataset(path)


def test_duplicate_relevant_uuid_rejected(tmp_path):
    payload = make_valid_payload()

    payload["cases"][0]["relevant_chunk_ids"] = [
        str(A),
        str(A),
    ]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="contains duplicate UUIDs",
    ):
        load_golden_dataset(path)


def test_duplicate_case_ids_rejected(tmp_path):
    payload = make_valid_payload()

    payload["cases"][1]["case_id"] = "postgresql-001"

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="Duplicate evaluation case IDs",
    ):
        load_golden_dataset(path)


def test_missing_case_field_rejected(tmp_path):
    payload = make_valid_payload()

    del payload["cases"][0]["query"]

    path = write_dataset(tmp_path, payload)

    with pytest.raises(
        ValueError,
        match="query must be a non-empty string",
    ):
        load_golden_dataset(path)
