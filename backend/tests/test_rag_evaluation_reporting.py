"""Unit tests for RAG quality evaluation reporting and formatting (T260030)."""

from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    CaseDifficulty,
    CitationRequirement,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
)
from app.evaluation.rag_diagnostics import (
    AnswerClassification,
    FailureRootCause,
    RAGCaseDiagnostic,
)
from app.evaluation.rag_reporting import (
    build_rag_quality_report,
    render_rag_evaluation_markdown,
)
from app.evaluation.rag_runner import EvaluationRunConfig


def test_build_and_render_report():
    docs = [RAGFixtureDocument(key="doc_1", title="Title", content="Content")]
    cases = [
        RAGTestCase(
            case_id="tc-1",
            query="Query 1",
            category=CaseCategory.FACTUAL_EXACT,
            difficulty=CaseDifficulty.EASY,
            expected_answerability=Answerability.ANSWERABLE,
            expected_document_keys=["doc_1"],
        ),
        RAGTestCase(
            case_id="tc-2",
            query="Query 2",
            category=CaseCategory.OUT_OF_DOMAIN,
            difficulty=CaseDifficulty.EASY,
            expected_answerability=Answerability.REFUSAL_REQUIRED,
            expected_document_keys=[],
            expected_citation_behavior=CitationRequirement.NO_CITATION,
        ),
    ]
    manifest = RAGDatasetManifest(
        dataset_id="test-report",
        version="1.0",
        description="desc",
        documents=docs,
        cases=cases,
    )
    diagnostics = [
        RAGCaseDiagnostic(
            case_id="tc-1",
            query="Query 1",
            category=CaseCategory.FACTUAL_EXACT.value,
            difficulty=CaseDifficulty.EASY.value,
            workspace_ref="workspace_alpha",
            retrieved_doc_keys=("doc_1",),
            retrieved_chunk_count=1,
            retrieval_latency_ms=10.0,
            similarity_scores=(0.95,),
            cross_tenant_chunks_count=0,
            negative_doc_retrieved=False,
            recall_at_1=1.0,
            recall_at_3=1.0,
            recall_at_5=1.0,
            precision_at_1=1.0,
            precision_at_3=0.33,
            precision_at_5=0.2,
            reciprocal_rank=1.0,
            classification=AnswerClassification.CORRECT_ANSWER,
            root_cause=FailureRootCause.NONE,
            passed=True,
        ),
        RAGCaseDiagnostic(
            case_id="tc-2",
            query="Query 2",
            category=CaseCategory.OUT_OF_DOMAIN.value,
            difficulty=CaseDifficulty.EASY.value,
            workspace_ref="workspace_alpha",
            retrieved_doc_keys=(),
            retrieved_chunk_count=0,
            retrieval_latency_ms=8.0,
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
            classification=AnswerClassification.CORRECT_REFUSAL,
            root_cause=FailureRootCause.CORRECT_REFUSAL,
            passed=True,
        ),
    ]
    config = EvaluationRunConfig(mode="full-rag", k=5)
    report = build_rag_quality_report(
        dataset=manifest,
        diagnostics=diagnostics,
        config=config,
        llm_model_name="mock-llm",
    )

    assert report["metadata"]["total_cases"] == 2
    assert report["retrieval_metrics"]["recall_at_5"] == 1.0
    assert report["retrieval_metrics"]["tenant_isolation_rate"] == 1.0
    assert "generation_metrics" in report
    assert report["generation_metrics"]["overall_pass_rate"] == 1.0

    md = render_rag_evaluation_markdown(report)
    assert "# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG" in md
    assert "100.0%" in md
