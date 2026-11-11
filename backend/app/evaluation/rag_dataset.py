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
    # Extended benchmark categories (T260033)
    EXACT_IDENTIFIER = "EXACT_IDENTIFIER"
    CROSS_LINGUAL = "CROSS_LINGUAL"
    MULTI_CHUNK = "MULTI_CHUNK"
    MALICIOUS_QUERY = "MALICIOUS_QUERY"


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

    # Extended ground truth (T260033). All optional so legacy datasets stay valid.
    # Chunk identity is "<document_key>#<chunk_index>" (see make_chunk_id).
    expected_chunk_ids: list[NonEmptyString] = Field(default_factory=list)
    evidence_phrases: list[NonEmptyString] = Field(default_factory=list)
    relevance_rationale: str | None = None
    tags: list[NonEmptyString] = Field(default_factory=list)


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


def make_chunk_id(document_key: str, chunk_index: int) -> str:
    """Stable, provisioning-independent chunk identity: '<document_key>#<chunk_index>'."""
    return f"{document_key}#{chunk_index}"


def validate_ground_truth(
    manifest: RAGDatasetManifest,
    *,
    require_rationale: bool = False,
    require_evidence: bool = False,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[str]:
    """Check ground-truth integrity against the corpus exactly as it is provisioned.

    Returns a list of human-readable problems (empty list means valid):
    - every expected chunk id references an existing chunk of an expected document
    - every evidence phrase occurs in an expected document, and the labelled chunks equal
      the chunks containing the evidence (no missing / spurious chunk labels)
    - expected documents live in the case workspace (tenant consistency)
    - refusal cases carry no positive labels
    - optionally, rationale / evidence are mandatory for answerable cases
    """
    from app.services.chunking import chunk_text

    problems: list[str] = []
    docs = {d.key: d for d in manifest.documents}
    chunks_by_id: dict[str, str] = {}
    for doc in manifest.documents:
        for ch in chunk_text(doc.content, chunk_size=chunk_size, overlap=overlap):
            chunks_by_id[make_chunk_id(doc.key, ch.index)] = ch.content

    for case in manifest.cases:
        cid = case.case_id
        answerable = case.expected_answerability == Answerability.ANSWERABLE

        for key in case.expected_document_keys:
            if docs[key].workspace_ref != case.workspace_ref:
                problems.append(
                    f"{cid}: expected document '{key}' is in workspace "
                    f"'{docs[key].workspace_ref}', case queries '{case.workspace_ref}'"
                )

        if not answerable:
            if case.expected_document_keys or case.expected_chunk_ids:
                problems.append(f"{cid}: refusal case must not have positive labels")
            continue

        if require_rationale and not (case.relevance_rationale or "").strip():
            problems.append(f"{cid}: missing relevance_rationale")
        if require_evidence and not case.evidence_phrases:
            problems.append(f"{cid}: missing evidence_phrases")

        expected_docs = set(case.expected_document_keys)
        labelled = set(case.expected_chunk_ids)

        for chunk_id in labelled:
            if chunk_id not in chunks_by_id:
                problems.append(f"{cid}: expected chunk '{chunk_id}' does not exist")
            elif chunk_id.rsplit("#", 1)[0] not in expected_docs:
                problems.append(
                    f"{cid}: expected chunk '{chunk_id}' is not part of an expected document"
                )

        if labelled and not case.evidence_phrases:
            problems.append(f"{cid}: chunk labels require evidence_phrases")

        # Chunks overlap, so the relevant chunks are exactly the chunks of expected
        # documents that contain an evidence phrase. Every phrase must be found, and the
        # labelled set must equal that derived set (no missing and no spurious labels).
        if case.evidence_phrases:
            derived: set[str] = set()
            for phrase in case.evidence_phrases:
                holders = {
                    chunk_id
                    for chunk_id, content in chunks_by_id.items()
                    if chunk_id.rsplit("#", 1)[0] in expected_docs and phrase in content
                }
                if not holders:
                    problems.append(
                        f"{cid}: evidence phrase {phrase!r} not found in any expected document"
                    )
                derived |= holders
            if labelled and labelled != derived:
                problems.append(
                    f"{cid}: chunk labels {sorted(labelled)} differ from chunks containing "
                    f"the evidence {sorted(derived)}"
                )

    return problems


def load_rag_dataset(path: str | Path) -> RAGDatasetManifest:
    """Load and validate a RAG evaluation dataset from a JSON file."""
    content = Path(path).read_text(encoding="utf-8")
    return RAGDatasetManifest.model_validate_json(content)
