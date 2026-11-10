"""Versioned evaluation dataset models and loaders for RAG quality benchmarks (T260030).

Defines schema for synthetic evaluation documents and test cases with granular
ground-truth labels: expected documents, answerability, facts, citation requirements,
and tenant isolation expectations.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class Answerability(StrEnum):
    ANSWERABLE = "ANSWERABLE"
    REFUSAL_REQUIRED = "REFUSAL_REQUIRED"


class CitationRequirement(StrEnum):
    MUST_CITE = "MUST_CITE"
    NO_CITATION = "NO_CITATION"
    FORBIDDEN_CITE = "FORBIDDEN_CITE"


class CaseCategory(StrEnum):
    FACTUAL_EXACT = "FACTUAL_EXACT"
    SEMANTIC_PARAPHRASE = "SEMANTIC_PARAPHRASE"
    MULTI_DOC = "MULTI_DOC"
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    CROSS_WORKSPACE = "CROSS_WORKSPACE"
    PROMPT_INJECTION = "PROMPT_INJECTION"


class CaseDifficulty(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class RAGFixtureDocument(BaseModel):
    """A synthetic document used in RAG quality evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: NonEmptyString
    title: NonEmptyString
    content: NonEmptyString
    workspace_ref: NonEmptyString = "workspace_alpha"


class RAGTestCase(BaseModel):
    """An evaluation test case with expected retrieval and generation behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: NonEmptyString
    query: NonEmptyString
    category: CaseCategory
    difficulty: CaseDifficulty = CaseDifficulty.MEDIUM
    language: NonEmptyString = "vi"
    workspace_ref: NonEmptyString = "workspace_alpha"

    expected_answerability: Answerability
    expected_document_keys: list[NonEmptyString] = Field(default_factory=list)
    negative_document_keys: list[NonEmptyString] = Field(default_factory=list)
    expected_facts: list[NonEmptyString] = Field(default_factory=list)
    expected_citation_behavior: CitationRequirement = CitationRequirement.MUST_CITE
    description: NonEmptyString = "RAG quality evaluation case"


class RAGDatasetManifest(BaseModel):
    """A portable, versioned dataset manifest for RAG quality evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: NonEmptyString
    version: NonEmptyString
    description: NonEmptyString

    documents: list[RAGFixtureDocument] = Field(min_length=1)
    cases: list[RAGTestCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "RAGDatasetManifest":
        doc_keys = [doc.key for doc in self.documents]
        if len(doc_keys) != len(set(doc_keys)):
            raise ValueError("Duplicate fixture document keys in manifest")

        case_ids = [c.case_id for c in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Duplicate case IDs in manifest")

        available_keys = set(doc_keys)

        for case in self.cases:
            # Check expected keys exist in documents
            for exp_key in case.expected_document_keys:
                if exp_key not in available_keys:
                    raise ValueError(
                        f"Unknown expected document key '{exp_key}' in case '{case.case_id}'"
                    )

            # Check negative keys exist in documents
            for neg_key in case.negative_document_keys:
                if neg_key not in available_keys:
                    raise ValueError(
                        f"Unknown negative document key '{neg_key}' in case '{case.case_id}'"
                    )

            # Mutual exclusivity of expected and negative keys
            overlap = set(case.expected_document_keys) & set(
                case.negative_document_keys
            )
            if overlap:
                raise ValueError(
                    f"Keys {overlap} cannot be both expected and negative in case '{case.case_id}'"
                )

            # Consistency checks
            if case.expected_answerability == Answerability.REFUSAL_REQUIRED:
                if case.expected_citation_behavior == CitationRequirement.MUST_CITE:
                    raise ValueError(
                        f"Case '{case.case_id}' requires refusal but specifies MUST_CITE"
                    )
            elif (
                case.expected_answerability == Answerability.ANSWERABLE
                and not case.expected_document_keys
            ):
                raise ValueError(
                    f"Answerable case '{case.case_id}' must specify at least one expected document key"
                )

        return self


def load_rag_dataset(path: str | Path) -> RAGDatasetManifest:
    """Load and validate a RAG evaluation dataset from a JSON file."""
    content = Path(path).read_text(encoding="utf-8")
    return RAGDatasetManifest.model_validate_json(content)
