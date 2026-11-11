"""Tests for extended RAG retrieval quality evaluation framework (T260033).

Covers:
- Extended dataset schema & strict ground-truth validation (validate_ground_truth)
- Multi-doc and multi-chunk recall deduplication and metric behavior
- Pure report comparison module (compare_reports and render_comparison_markdown)
- Backward compatibility with legacy 36-case dataset
"""

from pathlib import Path

import pytest

from app.evaluation.rag_comparison import (
    compare_reports,
    render_comparison_markdown,
)
from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    RAGDatasetManifest,
    RAGFixtureDocument,
    RAGTestCase,
    load_rag_dataset,
    make_chunk_id,
    validate_ground_truth,
)
from app.evaluation.rag_metrics import (
    dedupe_preserving_order,
    first_relevant_rank,
    recall_at_k,
)

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets" / "evaluation"
EXTENDED_DATASET_PATH = DATASETS_DIR / "rag_quality_dataset_extended_v1.json"
LEGACY_DATASET_PATH = DATASETS_DIR / "rag_quality_dataset_v2.json"


# ---------------------------------------------------------------------------
# 1. Dataset & Ground-Truth Validation Tests
# ---------------------------------------------------------------------------


def test_extended_dataset_manifest_and_ground_truth_valid():
    manifest = load_rag_dataset(EXTENDED_DATASET_PATH)
    assert manifest.dataset_id == "ai-knowledge-lab-rag-quality-extended"
    assert manifest.version == "1.0"
    assert len(manifest.documents) == 29
    assert len(manifest.cases) == 41

    # Verify extended categories
    categories = {c.category for c in manifest.cases}
    assert CaseCategory.EXACT_IDENTIFIER in categories
    assert CaseCategory.CROSS_LINGUAL in categories
    assert CaseCategory.MULTI_CHUNK in categories
    assert CaseCategory.MALICIOUS_QUERY in categories
    assert CaseCategory.AMBIGUOUS_QUERY in categories

    # Strict validation passes with zero errors
    errors = validate_ground_truth(
        manifest, require_rationale=True, require_evidence=True
    )
    assert errors == []


def test_validate_ground_truth_catches_invalid_chunk_ids():
    manifest = RAGDatasetManifest(
        dataset_id="test-validation",
        version="1.0",
        description="Test validation manifest",
        documents=[
            RAGFixtureDocument(
                key="doc_1",
                title="Doc 1",
                content="Short single chunk content here.",
            )
        ],
        cases=[
            RAGTestCase(
                case_id="tc-1",
                query="Query",
                category=CaseCategory.FACTUAL_EXACT,
                expected_answerability=Answerability.ANSWERABLE,
                expected_document_keys=["doc_1"],
                expected_chunk_ids=["doc_1#99"],  # Nonexistent chunk index
                evidence_phrases=["Short single chunk"],
                relevance_rationale="Rationale here",
            )
        ],
    )
    errors = validate_ground_truth(manifest, require_rationale=True, require_evidence=True)
    assert any("expected chunk 'doc_1#99' does not exist" in e for e in errors)


def test_validate_ground_truth_catches_missing_evidence_phrase():
    manifest = RAGDatasetManifest(
        dataset_id="test-validation",
        version="1.0",
        description="Test validation manifest",
        documents=[
            RAGFixtureDocument(
                key="doc_1",
                title="Doc 1",
                content="This is the real text content without that phrase.",
            )
        ],
        cases=[
            RAGTestCase(
                case_id="tc-2",
                query="Query",
                category=CaseCategory.FACTUAL_EXACT,
                expected_answerability=Answerability.ANSWERABLE,
                expected_document_keys=["doc_1"],
                expected_chunk_ids=["doc_1#0"],
                evidence_phrases=["completely nonexistent phrase in doc"],
                relevance_rationale="Rationale here",
            )
        ],
    )
    errors = validate_ground_truth(manifest, require_rationale=True, require_evidence=True)
    assert any("evidence phrase 'completely nonexistent phrase in doc' not found" in e for e in errors)


def test_validate_ground_truth_catches_refusal_with_expected_docs():
    from app.evaluation.rag_dataset import CitationRequirement

    manifest = RAGDatasetManifest(
        dataset_id="test-validation",
        version="1.0",
        description="Test validation manifest",
        documents=[
            RAGFixtureDocument(
                key="doc_1",
                title="Doc 1",
                content="Some document content.",
            )
        ],
        cases=[
            RAGTestCase(
                case_id="tc-3",
                query="Out of domain question",
                category=CaseCategory.OUT_OF_DOMAIN,
                expected_answerability=Answerability.REFUSAL_REQUIRED,
                expected_citation_behavior=CitationRequirement.NO_CITATION,
                expected_document_keys=["doc_1"],  # Refusal should have no expected docs
            )
        ],
    )
    errors = validate_ground_truth(manifest)
    assert any("refusal case must not have positive labels" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. Multi-Doc, Multi-Chunk & Deduplication Tests
# ---------------------------------------------------------------------------


def test_recall_at_k_prevents_duplicate_chunk_inflation():
    # If 3 chunks of the same expected doc are retrieved, recall must remain 1.0 (not 3.0)
    retrieved = ["doc_alpha", "doc_alpha", "doc_alpha", "doc_beta", "doc_gamma"]
    expected = {"doc_alpha"}
    assert recall_at_k(retrieved, expected, k=3) == 1.0
    assert recall_at_k(retrieved, expected, k=5) == 1.0

    # Multi-doc case where only 1 of 2 expected documents is retrieved
    expected_two = {"doc_alpha", "doc_delta"}
    assert recall_at_k(retrieved, expected_two, k=3) == 0.5


def test_dedupe_preserving_order():
    items = ["doc_b", "doc_a", "doc_b", "doc_c", "doc_a", "doc_d"]
    deduped = dedupe_preserving_order(items)
    assert deduped == ["doc_b", "doc_a", "doc_c", "doc_d"]
    assert dedupe_preserving_order([]) == []


def test_first_relevant_rank():
    retrieved = ["doc_x", "doc_y", "doc_target_b", "doc_target_a"]
    assert first_relevant_rank(retrieved, {"doc_target_a", "doc_target_b"}) == 3
    assert first_relevant_rank(retrieved, {"doc_target_a"}) == 4
    assert first_relevant_rank(retrieved, {"nonexistent"}) is None
    assert first_relevant_rank([], {"doc_target_a"}) is None


def test_make_chunk_id_format():
    assert make_chunk_id("doc_runbook", 2) == "doc_runbook#2"
    assert make_chunk_id("ext_api_spec", 0) == "ext_api_spec#0"


# ---------------------------------------------------------------------------
# 3. Report Comparison Module Tests
# ---------------------------------------------------------------------------


def _build_minimal_report(
    *,
    strategy: str,
    hit_1: float,
    hit_5: float,
    mrr_5: float,
    case_ranks: dict[str, int | None],
    lexical_cases: set[str],
) -> dict:
    case_diagnostics = []
    for cid, rank in case_ranks.items():
        doc_ranks = [f"doc_{i}" for i in range(1, 6)]
        if rank is not None and 1 <= rank <= 5:
            doc_ranks[rank - 1] = f"target_{cid}"
        diag = {
            "case_id": cid,
            "category": "EXACT_IDENTIFIER" if "ID" in cid else "CROSS_LINGUAL",
            "language": "en",
            "tags": ["test"],
            "expected_documents": [f"target_{cid}"],
            "expected_chunk_ids": [f"target_{cid}#0"],
            "retrieved_keys": doc_ranks,
            "retrieved_chunk_ids": [f"{k}#0" for k in doc_ranks],
            "first_relevant_doc_rank": rank,
            "first_relevant_chunk_rank": rank,
            "chunk_labeled": True,
            "chunk_hit_at_5": rank is not None and rank <= 5,
            "retrieval_provenance": (
                ["hybrid" if cid in lexical_cases else "dense"] * 5
            ),
        }
        case_diagnostics.append(diag)

    return {
        "metadata": {
            "dataset_id": "test-dataset",
            "dataset_version": "1.0",
            "retrieval_strategy": strategy,
            "database_name": "ailab_eval_test",
            "k": 5,
        },
        "retrieval_metrics": {
            "hit_rate_at_1": hit_1,
            "hit_rate_at_3": hit_1,
            "hit_rate_at_5": hit_5,
            "recall_at_1": hit_1,
            "recall_at_3": hit_1,
            "recall_at_5": hit_5,
            "precision_at_5": 0.2,
            "mrr_at_5": mrr_5,
            "retrieval_coverage": hit_5,
            "chunk_recall_at_5": hit_5,
            "chunk_mrr_at_5": mrr_5,
            "tenant_isolation_rate": 1.0,
            "empty_candidate_rate": 0.0,
            "empty_accepted_evidence_rate": 0.0,
        },
        "category_breakdown": {},
        "language_breakdown": {},
        "tag_breakdown": {},
        "cases": case_diagnostics,
    }


def test_compare_reports_detects_deltas_and_shifts():
    dense = _build_minimal_report(
        strategy="dense",
        hit_1=0.5,
        hit_5=1.0,
        mrr_5=0.75,
        case_ranks={"C-ID-01": 2, "C-XL-01": 1},
        lexical_cases=set(),
    )
    hybrid = _build_minimal_report(
        strategy="hybrid",
        hit_1=1.0,
        hit_5=1.0,
        mrr_5=1.0,
        case_ranks={"C-ID-01": 1, "C-XL-01": 1},  # C-ID-01 improved: rank 2 -> rank 1
        lexical_cases={"C-ID-01"},
    )

    comparison = compare_reports(dense, hybrid)
    assert comparison["aggregate"]["mrr_at_5"]["delta"] == pytest.approx(0.25)
    assert comparison["summary"]["doc_rank_improved"] == ["C-ID-01"]
    assert comparison["summary"]["doc_rank_regressed"] == []
    assert comparison["summary"]["doc_rank_unchanged_count"] == 1
    assert "C-ID-01" in comparison["summary"]["lexical_supported_cases"]

    md = render_comparison_markdown(comparison)
    assert "# So sánh Dense vs Hybrid" in md
    assert "C-ID-01" in md
    assert "improved" in md


# ---------------------------------------------------------------------------
# 4. Backward Compatibility Test
# ---------------------------------------------------------------------------


def test_legacy_dataset_backward_compatibility():
    legacy_manifest = load_rag_dataset(LEGACY_DATASET_PATH)
    assert legacy_manifest.dataset_id == "ai-knowledge-lab-rag-quality"
    assert legacy_manifest.version == "2.0"
    assert len(legacy_manifest.cases) == 36

    # Legacy dataset doesn't have evidence_phrases or expected_chunk_ids,
    # so require_rationale=False and require_evidence=False should pass 100% cleanly
    errors = validate_ground_truth(
        legacy_manifest, require_rationale=False, require_evidence=False
    )
    assert errors == []
