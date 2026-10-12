
"""Load fixture manifests and resolve real chunk references."""

from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.evaluation.models import GoldenDataset, GoldenQuery

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class FixtureDocument(BaseModel):
    """A document used to construct an evaluation corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: NonEmptyString
    title: NonEmptyString
    content: NonEmptyString


class FixtureCase(BaseModel):
    """An evaluation question labeled by document keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: NonEmptyString
    query: NonEmptyString
    relevant_document_keys: list[NonEmptyString] = Field(
        min_length=1
    )


class RetrievalFixtureManifest(BaseModel):
    """A portable, versioned retrieval evaluation fixture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: NonEmptyString
    version: NonEmptyString

    documents: list[FixtureDocument] = Field(min_length=1)
    cases: list[FixtureCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        document_keys = [doc.key for doc in self.documents]

        if len(document_keys) != len(set(document_keys)):
            raise ValueError("Duplicate fixture document keys")

        case_ids = [case.case_id for case in self.cases]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Duplicate fixture case IDs")

        available_keys = set(document_keys)

        for case in self.cases:
            relevant_keys = case.relevant_document_keys

            if len(relevant_keys) != len(set(relevant_keys)):
                raise ValueError(
                    f"Duplicate relevant document keys: {case.case_id}"
                )

            unknown_keys = set(relevant_keys) - available_keys

            if unknown_keys:
                raise ValueError(
                    f"Unknown document keys in {case.case_id}: "
                    f"{sorted(unknown_keys)}"
                )

        return self


def load_fixture_manifest(
    path: str | Path,
) -> RetrievalFixtureManifest:
    """Read and validate a portable evaluation fixture."""

    content = Path(path).read_text(encoding="utf-8")

    return RetrievalFixtureManifest.model_validate_json(
        content
    )


def build_fixture_golden_dataset(
    *,
    manifest: RetrievalFixtureManifest,
    chunk_ids_by_document_key: Mapping[
        str,
        Collection[UUID],
    ],
) -> GoldenDataset:
    """Resolve fixture document keys to persisted chunk UUIDs."""

    resolved_ids: dict[str, frozenset[UUID]] = {}

    for document in manifest.documents:
        chunk_ids = frozenset(
            chunk_ids_by_document_key.get(document.key, ())
        )

        if not chunk_ids:
            raise ValueError(
                "No persisted chunks for fixture document: "
                f"{document.key}"
            )

        resolved_ids[document.key] = chunk_ids

    cases: list[GoldenQuery] = []

    for case in manifest.cases:
        relevant_ids = frozenset(
            chunk_id
            for document_key in case.relevant_document_keys
            for chunk_id in resolved_ids[document_key]
        )

        cases.append(
            GoldenQuery(
                case_id=case.case_id,
                query=case.query,
                relevant_chunk_ids=relevant_ids,
            )
        )

    return GoldenDataset(
        dataset_id=manifest.dataset_id,
        version=manifest.version,
        cases=tuple(cases),
    )
