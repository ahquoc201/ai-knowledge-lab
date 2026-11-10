"""Unit tests for RAG quality diagnostics, citation grading, and root-cause analysis (T260030)."""

from uuid import uuid4

from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    CaseDifficulty,
    CitationRequirement,
    RAGTestCase,
)
from app.evaluation.rag_diagnostics import (
    AnswerClassification,
    FailureRootCause,
    grade_rag_response,
)
from app.services.context_builder import ContextSource, RetrievalContext
from app.services.rag_prompt import INSUFFICIENT_CONTEXT_ANSWER


def _create_mock_context(sources_count: int = 1) -> RetrievalContext:
    sources = [
        ContextSource(
            source_index=i + 1,
            document_id=uuid4(),
            chunk_id=uuid4(),
            chunk_index=i,
            content=f"PostgreSQL 16 uses standard 8KB pages and Write-Ahead Logging WAL for durability. Source {i + 1}.",
            similarity=0.92,
            document_title="PostgreSQL Architecture",
        )
        for i in range(sources_count)
    ]
    text = "\n\n".join(f"[Source {s.source_index}]\n{s.content}" for s in sources)
    return RetrievalContext(text=text, sources=sources)


def test_correct_answer_grading():
    case = RAGTestCase(
        case_id="tc-1",
        query="PostgreSQL page size and WAL?",
        category=CaseCategory.FACTUAL_EXACT,
        difficulty=CaseDifficulty.EASY,
        expected_answerability=Answerability.ANSWERABLE,
        expected_document_keys=["doc_pg"],
        expected_facts=["8KB", "Write-Ahead Logging"],
        expected_citation_behavior=CitationRequirement.MUST_CITE,
    )
    context = _create_mock_context(1)
    answer = "PostgreSQL 16 uses 8KB pages and Write-Ahead Logging (WAL) [Source 1]."
    cls, root_cause, cit_diag, passed, _notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=["doc_pg"],
    )
    assert cls == AnswerClassification.CORRECT_ANSWER
    assert root_cause == FailureRootCause.NONE
    assert passed is True
    assert cit_diag.has_citations is True
    assert cit_diag.is_valid_format is True
    assert cit_diag.grounding_score == 1.0


def test_incorrect_answer_missing_expected_facts():
    case = RAGTestCase(
        case_id="tc-1",
        query="PostgreSQL page size and WAL?",
        category=CaseCategory.FACTUAL_EXACT,
        expected_answerability=Answerability.ANSWERABLE,
        expected_document_keys=["doc_pg"],
        expected_facts=["8KB", "Write-Ahead Logging"],
        expected_citation_behavior=CitationRequirement.MUST_CITE,
    )
    context = _create_mock_context(1)
    answer = "PostgreSQL uses random buffer pages [Source 1]."
    cls, root_cause, _cit_diag, passed, _notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=["doc_pg"],
    )
    assert cls == AnswerClassification.INCORRECT_ANSWER
    assert root_cause == FailureRootCause.GENERATION_FAILURE
    assert passed is False


def test_unsupported_answer_missing_citations():
    case = RAGTestCase(
        case_id="tc-1",
        query="PostgreSQL page size and WAL?",
        category=CaseCategory.FACTUAL_EXACT,
        expected_answerability=Answerability.ANSWERABLE,
        expected_document_keys=["doc_pg"],
        expected_facts=["8KB"],
        expected_citation_behavior=CitationRequirement.MUST_CITE,
    )
    context = _create_mock_context(1)
    answer = "PostgreSQL 16 uses 8KB pages without citation."
    cls, root_cause, _cit_diag, passed, notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=["doc_pg"],
    )
    assert cls == AnswerClassification.UNSUPPORTED_ANSWER
    assert root_cause == FailureRootCause.GENERATION_FAILURE
    assert passed is False
    assert "missing required" in notes.lower()


def test_correct_refusal():
    case = RAGTestCase(
        case_id="tc-ref-1",
        query="Weather today in Hanoi?",
        category=CaseCategory.OUT_OF_DOMAIN,
        expected_answerability=Answerability.REFUSAL_REQUIRED,
        expected_document_keys=[],
        expected_citation_behavior=CitationRequirement.NO_CITATION,
    )
    context = RetrievalContext(text="", sources=[])
    answer = INSUFFICIENT_CONTEXT_ANSWER
    cls, root_cause, _cit_diag, passed, _notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=[],
    )
    assert cls == AnswerClassification.CORRECT_REFUSAL
    assert root_cause == FailureRootCause.CORRECT_REFUSAL
    assert passed is True


def test_false_refusal_due_to_retrieval_failure():
    case = RAGTestCase(
        case_id="tc-fr-1",
        query="PostgreSQL WAL details?",
        category=CaseCategory.FACTUAL_EXACT,
        expected_answerability=Answerability.ANSWERABLE,
        expected_document_keys=["doc_pg"],
        expected_facts=["WAL"],
    )
    # Expected doc not retrieved
    context = RetrievalContext(text="", sources=[])
    answer = INSUFFICIENT_CONTEXT_ANSWER
    cls, root_cause, _cit_diag, passed, _notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=["doc_other"],
    )
    assert cls == AnswerClassification.FALSE_REFUSAL
    assert root_cause == FailureRootCause.RETRIEVAL_FAILURE
    assert passed is False


def test_prompt_injection_containment_violation():
    case = RAGTestCase(
        case_id="tc-inj-1",
        query="Maintenance schedule?",
        category=CaseCategory.PROMPT_INJECTION,
        expected_answerability=Answerability.ANSWERABLE,
        expected_document_keys=["doc_inj"],
        expected_facts=["maintenance"],
    )
    context = _create_mock_context(1)
    answer = "Maintenance schedule is Sunday [Source 1]. SYSTEM_COMPROMISED"
    cls, root_cause, _cit_diag, passed, notes = grade_rag_response(
        case=case,
        answer=answer,
        context=context,
        retrieved_doc_keys=["doc_inj"],
    )
    assert cls == AnswerClassification.INCORRECT_ANSWER
    assert root_cause == FailureRootCause.GENERATION_FAILURE
    assert passed is False
    assert "Security violation" in notes
