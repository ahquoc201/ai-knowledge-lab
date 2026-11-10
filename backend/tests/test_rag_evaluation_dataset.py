"""Unit tests for RAG quality evaluation dataset models and validation (T260030)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    CitationRequirement,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
    load_rag_dataset,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "datasets"
    / "evaluation"
    / "rag_quality_dataset_v2.json"
)


def test_load_official_rag_quality_dataset():
    manifest = load_rag_dataset(FIXTURE_PATH)
    assert manifest.dataset_id == "ai-knowledge-lab-rag-quality"
    assert manifest.version == "2.0"
    assert len(manifest.documents) == 8
    assert len(manifest.cases) == 36

    # Verify categories presence
    categories = {c.category for c in manifest.cases}
    assert CaseCategory.FACTUAL_EXACT in categories
    assert CaseCategory.SEMANTIC_PARAPHRASE in categories
    assert CaseCategory.MULTI_DOC in categories
    assert CaseCategory.CROSS_WORKSPACE in categories
    assert CaseCategory.INSUFFICIENT_INFO in categories
    assert CaseCategory.OUT_OF_DOMAIN in categories
    assert CaseCategory.PROMPT_INJECTION in categories


def test_duplicate_document_keys_rejected():
    docs = [
        RAGFixtureDocument(key="doc_1", title="Doc 1", content="Text 1"),
        RAGFixtureDocument(key="doc_1", title="Doc 1 Dup", content="Text 2"),
    ]
    cases = [
        RAGTestCase(
            case_id="tc-1",
            query="test query",
            category=CaseCategory.FACTUAL_EXACT,
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_1"],
        )
    ]
    with pytest.raises(ValidationError, match="Duplicate fixture document keys"):
        RAGDatasetManifest(
            dataset_id="test",
            version="1.0",
            description="test",
            documents=docs,
            cases=cases,
        )


def test_duplicate_case_ids_rejected():
    docs = [RAGFixtureDocument(key="doc_1", title="Doc 1", content="Text 1")]
    cases = [
        RAGTestCase(
            case_id="tc-1",
            query="query 1",
            category=CaseCategory.FACTUAL_EXACT,
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_1"],
        ),
        RAGTestCase(
            case_id="tc-1",
            query="query 2",
            category=CaseCategory.FACTUAL_EXACT,
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_1"],
        ),
    ]
    with pytest.raises(ValidationError, match="Duplicate case IDs"):
        RAGDatasetManifest(
            dataset_id="test",
            version="1.0",
            description="test",
            documents=docs,
            cases=cases,
        )


def test_unknown_document_key_rejected():
    docs = [RAGFixtureDocument(key="doc_1", title="Doc 1", content="Text 1")]
    cases = [
        RAGTestCase(
            case_id="tc-1",
            query="query 1",
            category=CaseCategory.FACTUAL_EXACT,
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_non_existent"],
        )
    ]
    with pytest.raises(ValidationError, match="Unknown expected document key"):
        RAGDatasetManifest(
            dataset_id="test",
            version="1.0",
            description="test",
            documents=docs,
            cases=cases,
        )


def test_refusal_with_must_cite_rejected():
    docs = [RAGFixtureDocument(key="doc_1", title="Doc 1", content="Text 1")]
    cases = [
        RAGTestCase(
            case_id="tc-1",
            query="query 1",
            category=CaseCategory.INSUFFICIENT_INFO,
            expected_answerability=Answerability.REFUSAL_REQUIRED,
            expected_document_keys=[],
            expected_citation_behavior=CitationRequirement.MUST_CITE,
        )
    ]
    with pytest.raises(
        ValidationError, match="requires refusal but specifies MUST_CITE"
    ):
        RAGDatasetManifest(
            dataset_id="test",
            version="1.0",
            description="test",
            documents=docs,
            cases=cases,
        )
