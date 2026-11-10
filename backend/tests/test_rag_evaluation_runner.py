"""Unit and integration tests for RAG evaluation runner (T260030)."""

import pytest

from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    CaseDifficulty,
    CitationRequirement,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
)
from app.evaluation.rag_runner import (
    EvaluationRunConfig,
    InMemoryCorpusRetriever,
    run_rag_evaluation,
)
from app.llm.base import LLMMessage, LLMProvider


class MockLLMProvider(LLMProvider):
    async def generate(self, messages: list[LLMMessage], **kwargs) -> str:
        # Simple mock responding with fact and citation
        return "PostgreSQL 16 uses 8KB pages and Write-Ahead Logging WAL [Source 1]."


@pytest.fixture
def mini_dataset() -> RAGDatasetManifest:
    docs = [
        RAGFixtureDocument(
            key="doc_pg",
            title="PostgreSQL Doc",
            content="PostgreSQL 16 uses 8KB pages and Write-Ahead Logging WAL for durability.",
            workspace_ref="workspace_alpha",
        ),
        RAGFixtureDocument(
            key="doc_beta",
            title="Beta Doc",
            content="Confidential Beta project budget 1000 USD.",
            workspace_ref="workspace_beta",
        ),
    ]
    cases = [
        RAGTestCase(
            case_id="case-1",
            query="PostgreSQL page size and WAL?",
            category=CaseCategory.FACTUAL_EXACT,
            difficulty=CaseDifficulty.EASY,
            workspace_ref="workspace_alpha",
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_pg"],
            expected_facts=["8KB", "WAL"],
            expected_citation_behavior=CitationRequirement.MUST_CITE,
        ),
        RAGTestCase(
            case_id="case-tenant-iso",
            query="Confidential Beta budget?",
            category=CaseCategory.CROSS_WORKSPACE,
            difficulty=CaseDifficulty.HARD,
            workspace_ref="workspace_alpha",
            expected_answerability=Answerability.REFUSAL_REQUIRED,
            expected_document_keys=[],
            negative_document_keys=["doc_beta"],
            expected_citation_behavior=CitationRequirement.NO_CITATION,
        ),
    ]
    return RAGDatasetManifest(
        dataset_id="mini-test",
        version="1.0",
        description="mini test dataset",
        documents=docs,
        cases=cases,
    )


@pytest.mark.anyio
async def test_in_memory_retriever_isolation_and_search(mini_dataset):
    retriever = InMemoryCorpusRetriever(mini_dataset.documents)

    # Search inside workspace_alpha
    results_alpha = await retriever.search(
        "PostgreSQL page size", workspace_ref="workspace_alpha", limit=5
    )
    assert len(results_alpha) > 0
    doc_key = retriever.get_document_key_for_chunk(results_alpha[0].chunk.id)
    assert doc_key == "doc_pg"

    # Search query asking about Beta from workspace_alpha must return 0 Beta chunks
    results_cross = await retriever.search(
        "Confidential Beta budget", workspace_ref="workspace_alpha", limit=5
    )
    for res in results_cross:
        assert retriever.get_workspace_ref_for_chunk(res.chunk.id) == "workspace_alpha"


@pytest.mark.anyio
async def test_run_rag_evaluation_retrieval_only(mini_dataset):
    retriever = InMemoryCorpusRetriever(mini_dataset.documents)
    config = EvaluationRunConfig(mode="retrieval-only", k=5)
    diagnostics = await run_rag_evaluation(
        dataset=mini_dataset,
        retriever=retriever,
        config=config,
    )
    assert len(diagnostics) == 2
    assert diagnostics[0].passed is True
    assert diagnostics[0].recall_at_5 == 1.0
    assert diagnostics[1].passed is True  # Isolation held


@pytest.mark.anyio
async def test_run_rag_evaluation_full_rag(mini_dataset):
    retriever = InMemoryCorpusRetriever(mini_dataset.documents)
    config = EvaluationRunConfig(mode="full-rag", k=5)
    mock_llm = MockLLMProvider()
    diagnostics = await run_rag_evaluation(
        dataset=mini_dataset,
        retriever=retriever,
        config=config,
        llm=mock_llm,
    )
    assert len(diagnostics) == 2
    assert diagnostics[0].passed is True
    assert diagnostics[0].classification.value == "CORRECT_ANSWER"
