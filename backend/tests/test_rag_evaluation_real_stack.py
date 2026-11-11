"""Unit and integration tests for real-stack pgvector RAG evaluation (T260031).

Tests:
1. Database safety enforcement (prohibition of 'ailab').
2. Real fixture provisioning & automatic cleanup.
3. RealPgVectorCorpusRetriever search & sub-stage latency profiling.
4. FailureRootCause 9 granular classifications.
5. Empty candidate & accepted evidence rate metrics.
6. Partial recall calculation on multi-document expected cases.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    CaseDifficulty,
    CitationRequirement,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
)
from app.evaluation.rag_diagnostics import FailureRootCause, RAGCaseDiagnostic
from app.evaluation.rag_metrics import (
    empty_accepted_evidence_rate,
    empty_candidate_rate,
    recall_at_k,
)
from app.evaluation.real_fixture_provisioner import (
    provision_real_rag_fixtures,
    verify_database_safety,
)
from app.evaluation.real_pgvector_retriever import RealPgVectorCorpusRetriever

TEST_DATABASE_URL = (
    "postgresql+asyncpg://ailab:local_only_change_me@127.0.0.1:15432/ailab_eval_test"
)


def test_verify_database_safety_rejects_ailab() -> None:
    """verify_database_safety must raise PermissionError if pointed at historical 'ailab' DB."""
    with pytest.raises(PermissionError) as exc_info:
        verify_database_safety("postgresql+asyncpg://user:pass@127.0.0.1:5432/ailab")
    assert "CRITICAL DATA SAFETY VIOLATION" in str(exc_info.value)
    assert "ailab" in str(exc_info.value)

    # Isolated test database must pass
    db_name = verify_database_safety(
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/ailab_eval_test"
    )
    assert db_name == "ailab_eval_test"


def test_failure_root_causes_completeness() -> None:
    """Ensure all 9 requested failure root causes are present."""
    expected_causes = {
        "QUERY_EMBEDDING_FAILURE",
        "VECTOR_RETRIEVAL_FAILURE",
        "WRONG_DOCUMENT_RANKING",
        "SIMILARITY_FILTER_REJECTION",
        "CONTEXT_ASSEMBLY_FAILURE",
        "LLM_GENERATION_FAILURE",
        "CITATION_VALIDATION_FAILURE",
        "CORRECT_GUARDRAIL_REFUSAL",
        "UNKNOWN_ROOT_CAUSE",
    }
    actual_causes = {c.value for c in FailureRootCause}
    assert expected_causes.issubset(actual_causes)


def test_empty_candidate_and_evidence_rates() -> None:
    """Verify calculation of empty candidate and empty accepted evidence rates."""
    d1 = RAGCaseDiagnostic(
        case_id="c1",
        query="q1",
        category="FACTUAL_EXACT",
        difficulty="EASY",
        workspace_ref="w1",
        retrieved_doc_keys=("d1",),
        retrieved_chunk_count=1,
        retrieval_latency_ms=10.0,
        similarity_scores=(0.9,),
        cross_tenant_chunks_count=0,
        negative_doc_retrieved=False,
        recall_at_1=1.0,
        recall_at_3=1.0,
        recall_at_5=1.0,
        precision_at_1=1.0,
        precision_at_3=0.33,
        precision_at_5=0.2,
        reciprocal_rank=1.0,
        candidates_count=2,
        accepted_evidence_count=1,
    )
    d2 = RAGCaseDiagnostic(
        case_id="c2",
        query="q2",
        category="FACTUAL_EXACT",
        difficulty="EASY",
        workspace_ref="w1",
        retrieved_doc_keys=(),
        retrieved_chunk_count=0,
        retrieval_latency_ms=10.0,
        similarity_scores=(),
        cross_tenant_chunks_count=0,
        negative_doc_retrieved=False,
        recall_at_1=0.0,
        recall_at_3=0.0,
        recall_at_5=0.0,
        precision_at_1=0.0,
        precision_at_3=0.0,
        precision_at_5=0.0,
        reciprocal_rank=0.0,
        candidates_count=0,
        accepted_evidence_count=0,
    )
    d3 = RAGCaseDiagnostic(
        case_id="c3",
        query="q3",
        category="FACTUAL_EXACT",
        difficulty="EASY",
        workspace_ref="w1",
        retrieved_doc_keys=("d2",),
        retrieved_chunk_count=1,
        retrieval_latency_ms=10.0,
        similarity_scores=(0.5,),
        cross_tenant_chunks_count=0,
        negative_doc_retrieved=False,
        recall_at_1=0.0,
        recall_at_3=0.0,
        recall_at_5=0.0,
        precision_at_1=0.0,
        precision_at_3=0.0,
        precision_at_5=0.0,
        reciprocal_rank=0.0,
        candidates_count=3,
        accepted_evidence_count=0,  # Filtered out during context assembly
    )

    diagnostics = [d1, d2, d3]
    candidate_counts = [d.candidates_count for d in diagnostics]
    accepted_counts = [d.accepted_evidence_count for d in diagnostics]

    assert empty_candidate_rate(candidate_counts) == pytest.approx(1 / 3)
    assert empty_accepted_evidence_rate(accepted_counts) == pytest.approx(2 / 3)


def test_multi_document_partial_recall() -> None:
    """Verify that multi-document queries with partial retrieval produce fractional recall."""
    expected = ["doc_a", "doc_b"]
    retrieved_full = ["doc_a", "doc_b", "doc_c"]
    retrieved_partial = ["doc_a", "doc_x", "doc_y"]
    retrieved_none = ["doc_x", "doc_y"]

    assert recall_at_k(retrieved_full, expected, 3) == pytest.approx(1.0)
    assert recall_at_k(retrieved_partial, expected, 3) == pytest.approx(0.5)
    assert recall_at_k(retrieved_none, expected, 3) == pytest.approx(0.0)


@pytest.mark.anyio
async def test_real_pgvector_fixture_provisioning_and_cleanup() -> None:
    """Test provisioning and cleanup in isolated ailab_eval_test database."""
    manifest = RAGDatasetManifest(
        dataset_id="test-fixture-lifecycle",
        version="1.0",
        description="Mini fixture for test lifecycle verification",
        documents=[
            RAGFixtureDocument(
                key="doc_real_test_1",
                title="Real Stack Pgvector Test",
                content="PostgreSQL 16 with pgvector extension enables fast vector similarity search.",
                workspace_ref="workspace_alpha",
            ),
        ],
        cases=[
            RAGTestCase(
                case_id="tc-real-1",
                query="PostgreSQL vector similarity search?",
                category=CaseCategory.FACTUAL_EXACT,
                difficulty=CaseDifficulty.EASY,
                workspace_ref="workspace_alpha",
                expected_answerability=Answerability.ANSWERABLE,
                expected_document_keys=["doc_real_test_1"],
                expected_facts=["pgvector"],
                expected_citation_behavior=CitationRequirement.MUST_CITE,
            )
        ],
    )

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with provision_real_rag_fixtures(engine=engine, manifest=manifest) as env:
            assert env.database_name == "ailab_eval_test"
            assert env.total_documents == 1
            assert env.total_chunks == 1
            assert "doc_real_test_1" in env.document_id_map
            assert "workspace_alpha" in env.workspace_map

            retriever = RealPgVectorCorpusRetriever(
                session_factory=session_factory,
                env=env,
            )

            # Perform search in matching workspace
            results = await retriever.search(
                "pgvector similarity search",
                workspace_ref="workspace_alpha",
                limit=3,
            )
            assert len(results) >= 1
            assert retriever.last_embedding_latency_ms > 0
            assert retriever.last_vector_latency_ms >= 0
            assert retriever.last_candidates_count >= 1

            matched_chunk = results[0].chunk
            assert (
                retriever.get_document_key_for_chunk(matched_chunk.id)
                == "doc_real_test_1"
            )
            assert (
                retriever.get_workspace_ref_for_chunk(matched_chunk.id)
                == "workspace_alpha"
            )

            # Search in different workspace should respect tenant isolation
            results_beta = await retriever.search(
                "pgvector similarity search",
                workspace_ref="workspace_beta",
                limit=3,
            )
            assert len(results_beta) == 0

    finally:
        await engine.dispose()
