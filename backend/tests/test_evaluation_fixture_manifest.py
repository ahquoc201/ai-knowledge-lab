
"""Tests for portable retrieval evaluation fixtures."""

from copy import deepcopy
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.evaluation.fixture_manifest import (
    RetrievalFixtureManifest,
    build_fixture_golden_dataset,
    load_fixture_manifest,
)

A = UUID(int=1)
B = UUID(int=2)
C = UUID(int=3)


def make_payload() -> dict:
    return {
        "dataset_id": "test-retrieval",
        "version": "1.0",
        "documents": [
            {
                "key": "postgresql",
                "title": "PostgreSQL",
                "content": "PostgreSQL supports transactions.",
            },
            {
                "key": "redis",
                "title": "Redis",
                "content": "Redis supports caching.",
            },
        ],
        "cases": [
            {
                "case_id": "q1",
                "query": "What supports transactions?",
                "relevant_document_keys": ["postgresql"],
            },
            {
                "case_id": "q2",
                "query": "What supports caching?",
                "relevant_document_keys": ["redis"],
            },
        ],
    }


def make_manifest() -> RetrievalFixtureManifest:
    return RetrievalFixtureManifest.model_validate(
        make_payload()
    )


def test_load_real_fixture_manifest():
    path = (
        Path(__file__).resolve().parents[1]
        / "datasets"
        / "evaluation"
        / "retrieval_fixtures.json"
    )

    manifest = load_fixture_manifest(path)

    assert manifest.dataset_id == "ai-knowledge-lab-retrieval"
    assert manifest.version == "1.0"
    assert len(manifest.documents) == 4
    assert len(manifest.cases) == 8


def test_build_golden_dataset_resolves_chunk_ids():
    manifest = make_manifest()

    dataset = build_fixture_golden_dataset(
        manifest=manifest,
        chunk_ids_by_document_key={
            "postgresql": [A],
            "redis": [B],
        },
    )

    assert dataset.dataset_id == "test-retrieval"
    assert dataset.version == "1.0"
    assert [case.case_id for case in dataset.cases] == [
        "q1",
        "q2",
    ]
    assert dataset.cases[0].relevant_chunk_ids == frozenset({A})
    assert dataset.cases[1].relevant_chunk_ids == frozenset({B})


def test_multiple_chunks_per_document_supported():
    dataset = build_fixture_golden_dataset(
        manifest=make_manifest(),
        chunk_ids_by_document_key={
            "postgresql": [A, B],
            "redis": [C],
        },
    )

    assert dataset.cases[0].relevant_chunk_ids == frozenset(
        {A, B}
    )
    assert dataset.cases[1].relevant_chunk_ids == frozenset(
        {C}
    )


def test_missing_persisted_chunks_rejected():
    with pytest.raises(
        ValueError,
        match="No persisted chunks for fixture document: redis",
    ):
        build_fixture_golden_dataset(
            manifest=make_manifest(),
            chunk_ids_by_document_key={
                "postgresql": [A],
            },
        )


def test_duplicate_document_keys_rejected():
    payload = make_payload()
    payload["documents"].append(
        deepcopy(payload["documents"][0])
    )

    with pytest.raises(
        ValidationError,
        match="Duplicate fixture document keys",
    ):
        RetrievalFixtureManifest.model_validate(payload)


def test_duplicate_case_ids_rejected():
    payload = make_payload()
    payload["cases"][1]["case_id"] = "q1"

    with pytest.raises(
        ValidationError,
        match="Duplicate fixture case IDs",
    ):
        RetrievalFixtureManifest.model_validate(payload)


def test_unknown_document_reference_rejected():
    payload = make_payload()
    payload["cases"][0]["relevant_document_keys"] = [
        "unknown-document"
    ]

    with pytest.raises(
        ValidationError,
        match="Unknown document keys",
    ):
        RetrievalFixtureManifest.model_validate(payload)


def test_duplicate_relevant_document_keys_rejected():
    payload = make_payload()
    payload["cases"][0]["relevant_document_keys"] = [
        "postgresql",
        "postgresql",
    ]

    with pytest.raises(
        ValidationError,
        match="Duplicate relevant document keys",
    ):
        RetrievalFixtureManifest.model_validate(payload)


def test_empty_document_content_rejected():
    payload = make_payload()
    payload["documents"][0]["content"] = "   "

    with pytest.raises(ValidationError):
        RetrievalFixtureManifest.model_validate(payload)


def test_empty_relevant_documents_rejected():
    payload = make_payload()
    payload["cases"][0]["relevant_document_keys"] = []

    with pytest.raises(ValidationError):
        RetrievalFixtureManifest.model_validate(payload)


def test_unexpected_fields_rejected():
    payload = make_payload()
    payload["documents"][0]["unexpected_field"] = True

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        RetrievalFixtureManifest.model_validate(payload)


def test_missing_manifest_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fixture_manifest(
            tmp_path / "missing_fixture.json"
        )


def test_invalid_manifest_json(tmp_path):
    path = tmp_path / "invalid_fixture.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_fixture_manifest(path)
