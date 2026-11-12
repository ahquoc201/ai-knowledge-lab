"""Tests for independent cross-lingual holdout RAG evaluation framework (T260035).

Covers:
- Holdout dataset schema & strict ground-truth validation (validate_ground_truth)
- Independence and non-overlap with legacy v2 and extended v1 datasets
- SHA-256 reproducibility and checksum validation
- Answerability and denominator splitting (ANSWERABLE vs REFUSAL_REQUIRED)
- Multi-doc and multi-chunk ground-truth integrity
- Backward compatibility across all three evaluation manifests
- Report comparison parsing and deterministic rank shift tracking
"""

import hashlib
import json
from pathlib import Path

from app.evaluation.rag_comparison import (
    compare_reports,
    render_comparison_markdown,
)
from app.evaluation.rag_dataset import (
    Answerability,
    CaseCategory,
    RAGDatasetManifest,
    load_rag_dataset,
    validate_ground_truth,
)

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets" / "evaluation"
HOLDOUT_DATASET_PATH = DATASETS_DIR / "rag_quality_dataset_holdout_v1.json"
HOLDOUT_CHECKSUM_PATH = DATASETS_DIR / "rag_quality_dataset_holdout_v1.sha256"
EXTENDED_DATASET_PATH = DATASETS_DIR / "rag_quality_dataset_extended_v1.json"
LEGACY_DATASET_PATH = DATASETS_DIR / "rag_quality_dataset_v2.json"
REPORTS_DIR = DATASETS_DIR / "reports"


# ---------------------------------------------------------------------------
# 1. Dataset & Ground-Truth Validation Tests
# ---------------------------------------------------------------------------


def test_holdout_dataset_manifest_and_ground_truth_valid():
    """Verify holdout dataset conforms to RAGDatasetManifest with zero validation errors."""
    manifest = load_rag_dataset(HOLDOUT_DATASET_PATH)
    assert manifest.dataset_id == "ai-knowledge-lab-rag-quality-holdout"
    assert manifest.version == "1.0"
    assert len(manifest.documents) == 14
    assert len(manifest.cases) == 35

    # Verify categories present
    categories = {c.category for c in manifest.cases}
    assert CaseCategory.CROSS_LINGUAL in categories
    assert CaseCategory.EXACT_IDENTIFIER in categories
    assert CaseCategory.SEMANTIC_PARAPHRASE in categories
    assert CaseCategory.AMBIGUOUS_QUERY in categories
    assert CaseCategory.MULTI_DOC in categories
    assert CaseCategory.MULTI_CHUNK in categories
    assert CaseCategory.CROSS_WORKSPACE in categories
    assert CaseCategory.OUT_OF_DOMAIN in categories
    assert CaseCategory.PROMPT_INJECTION in categories
    assert CaseCategory.INSUFFICIENT_INFO in categories

    # Strict ground truth validation with rationale and evidence requirements
    errors = validate_ground_truth(
        manifest,
        require_rationale=True,
        require_evidence=True,
        chunk_size=1000,
        overlap=200,
    )
    assert errors == [], f"Holdout dataset validation errors: {errors}"


def test_holdout_dataset_sha256_checksum():
    """Verify holdout dataset file exactly matches its frozen SHA-256 checksum."""
    raw_bytes = HOLDOUT_DATASET_PATH.read_bytes()
    computed_sha = hashlib.sha256(raw_bytes).hexdigest()

    checksum_content = HOLDOUT_CHECKSUM_PATH.read_text(encoding="utf-8").strip()
    expected_sha = checksum_content.split()[0]

    assert computed_sha == expected_sha, (
        f"Holdout dataset SHA-256 mismatch! Expected {expected_sha}, got {computed_sha}"
    )


# ---------------------------------------------------------------------------
# 2. Independence and Non-Overlap Tests
# ---------------------------------------------------------------------------


def test_holdout_dataset_is_strictly_independent():
    """Verify holdout documents and cases have zero key overlap with legacy and extended datasets."""
    holdout = load_rag_dataset(HOLDOUT_DATASET_PATH)
    extended = load_rag_dataset(EXTENDED_DATASET_PATH)
    legacy = load_rag_dataset(LEGACY_DATASET_PATH)

    holdout_doc_keys = {d.key for d in holdout.documents}
    extended_doc_keys = {d.key for d in extended.documents}
    legacy_doc_keys = {d.key for d in legacy.documents}

    # Document keys must be 100% disjoint
    assert holdout_doc_keys.isdisjoint(extended_doc_keys), (
        f"Overlap with extended docs: {holdout_doc_keys & extended_doc_keys}"
    )
    assert holdout_doc_keys.isdisjoint(legacy_doc_keys), (
        f"Overlap with legacy docs: {holdout_doc_keys & legacy_doc_keys}"
    )

    holdout_case_ids = {c.case_id for c in holdout.cases}
    extended_case_ids = {c.case_id for c in extended.cases}
    legacy_case_ids = {c.case_id for c in legacy.cases}

    # Case IDs must be 100% disjoint
    assert holdout_case_ids.isdisjoint(extended_case_ids), (
        f"Overlap with extended cases: {holdout_case_ids & extended_case_ids}"
    )
    assert holdout_case_ids.isdisjoint(legacy_case_ids), (
        f"Overlap with legacy cases: {holdout_case_ids & legacy_case_ids}"
    )


# ---------------------------------------------------------------------------
# 3. Denominators and Answerability Consistency
# ---------------------------------------------------------------------------


def test_holdout_denominators_and_refusal_exclusion():
    """Verify answerable vs refusal case partitioning in holdout benchmark."""
    holdout = load_rag_dataset(HOLDOUT_DATASET_PATH)

    answerable = [
        c for c in holdout.cases if c.expected_answerability == Answerability.ANSWERABLE
    ]
    refusal = [
        c
        for c in holdout.cases
        if c.expected_answerability == Answerability.REFUSAL_REQUIRED
    ]

    assert len(answerable) == 30
    assert len(refusal) == 5
    assert len(answerable) + len(refusal) == 35

    # Every answerable case must have expected document keys
    for case in answerable:
        assert len(case.expected_document_keys) >= 1

    # Every refusal case must have empty expected documents
    for case in refusal:
        assert len(case.expected_document_keys) == 0


def test_holdout_cross_workspace_partitioning():
    """Verify CROSS_WORKSPACE cases distinguish retrieval from tenant isolation."""
    holdout = load_rag_dataset(HOLDOUT_DATASET_PATH)
    cw_cases = [c for c in holdout.cases if c.category == CaseCategory.CROSS_WORKSPACE]

    assert len(cw_cases) == 3
    # 2 unauthorized access attempts from alpha
    unauth = [
        c
        for c in cw_cases
        if c.workspace_ref == "workspace_alpha"
        and c.expected_answerability == Answerability.REFUSAL_REQUIRED
    ]
    assert len(unauth) == 2
    for c in unauth:
        assert len(c.negative_document_keys) >= 1

    # 1 authorized query inside beta
    auth = [
        c
        for c in cw_cases
        if c.workspace_ref == "workspace_beta"
        and c.expected_answerability == Answerability.ANSWERABLE
    ]
    assert len(auth) == 1
    assert auth[0].expected_document_keys == ["holdout_beta_billing_audit"]


# ---------------------------------------------------------------------------
# 4. Multi-Doc and Multi-Chunk Integrity
# ---------------------------------------------------------------------------


def test_holdout_multi_doc_cases():
    """Verify all MULTI_DOC cases specify at least two expected documents."""
    holdout = load_rag_dataset(HOLDOUT_DATASET_PATH)
    md_cases = [c for c in holdout.cases if c.category == CaseCategory.MULTI_DOC]

    assert len(md_cases) == 3
    for case in md_cases:
        assert len(case.expected_document_keys) >= 2


def test_holdout_multi_chunk_cases():
    """Verify all MULTI_CHUNK cases target chunks within the long runbook document."""
    holdout = load_rag_dataset(HOLDOUT_DATASET_PATH)
    mc_cases = [c for c in holdout.cases if c.category == CaseCategory.MULTI_CHUNK]

    assert len(mc_cases) == 3
    for case in mc_cases:
        assert case.expected_document_keys == ["holdout_vi_incident_runbook"]
        assert len(case.expected_chunk_ids) >= 1
        assert all(cid.startswith("holdout_vi_incident_runbook#") for cid in case.expected_chunk_ids)


# ---------------------------------------------------------------------------
# 5. Backward Compatibility across all 3 Benchmark Manifests
# ---------------------------------------------------------------------------


def test_all_evaluation_datasets_valid():
    """Ensure all three manifests load and validate simultaneously without regression."""
    for path in (LEGACY_DATASET_PATH, EXTENDED_DATASET_PATH, HOLDOUT_DATASET_PATH):
        manifest = load_rag_dataset(path)
        assert isinstance(manifest, RAGDatasetManifest)
        assert len(manifest.documents) >= 8
        assert len(manifest.cases) >= 35


# ---------------------------------------------------------------------------
# 6. Report Comparison Integrity
# ---------------------------------------------------------------------------


def test_holdout_comparison_reports_consistent():
    """Verify that committed holdout reports load and compare deterministically."""
    dense_path = REPORTS_DIR / "rag_quality_report_holdout_dense.json"
    hybrid_path = REPORTS_DIR / "rag_quality_report_holdout_hybrid.json"

    assert dense_path.exists(), "Dense holdout report missing"
    assert hybrid_path.exists(), "Hybrid holdout report missing"

    dense_rep = json.loads(dense_path.read_text(encoding="utf-8"))
    hybrid_rep = json.loads(hybrid_path.read_text(encoding="utf-8"))

    comp = compare_reports(dense_rep, hybrid_rep)
    assert comp["metadata"]["dataset_id"] == "ai-knowledge-lab-rag-quality-holdout"
    assert comp["metadata"]["dataset_version"] == "1.0"
    assert comp["summary"]["total_cases"] == 35
    assert comp["summary"]["answerable_cases"] == 30

    md = render_comparison_markdown(comp)
    assert "# So sánh Dense vs Hybrid — `ai-knowledge-lab-rag-quality-holdout` v`1.0`" in md
    assert "EXACT_IDENTIFIER" in md
    assert "CROSS_LINGUAL" in md
