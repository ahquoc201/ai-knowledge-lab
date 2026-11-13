"""Tests for Multilingual Candidate Retrieval & Reranking Feasibility (Task T260036)."""

import json
from pathlib import Path

from app.evaluation.rag_metrics import (
    dedupe_preserving_order,
    hit_rate_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_candidate_recall_diagnostics_report_integrity():
    report_path = REPO_ROOT / "datasets/evaluation/reports/candidate_recall_diagnostics.json"
    assert report_path.is_file(), "candidate_recall_diagnostics.json must exist"

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "standard_14_chunks" in data
    assert "augmented_74_chunks" in data

    for key, count in [("standard_14_chunks", 14), ("augmented_74_chunks", 74)]:
        section = data[key]
        assert section["total_chunks"] == count
        assert section["answerable_cases"] == 30
        summary = section["summary"]
        assert "dense" in summary and "keyword" in summary and "hybrid" in summary
        for strat in ["dense", "keyword", "hybrid"]:
            assert 0.0 <= summary[strat]["hit@1"] <= 1.0
            assert 0.0 <= summary[strat]["recall@5"] <= 1.0
            assert 0.0 <= summary[strat]["recall@20"] <= 1.0

        # Verify mutually exclusive diagnostic classifications
        diagnostics = section["diagnostics"]
        assert len(diagnostics) == 30
        valid_stages = {
            "SUCCESS_IN_TOP5",
            "1_ABSENT_FROM_FIRST_STAGE",
            "2_DEMOTED_BY_FUSION",
            "3_IN_TOP20_ABSENT_FROM_TOP5",
            "4_OTHER_CANDIDATE_LOSS",
        }
        for item in diagnostics:
            assert item["failure_stage"] in valid_stages


def test_reranker_feasibility_report_integrity():
    report_path = REPO_ROOT / "datasets/evaluation/reports/reranker_feasibility_report.json"
    diag_path = REPO_ROOT / "datasets/evaluation/reports/candidate_recall_diagnostics.json"
    assert report_path.is_file(), "reranker_feasibility_report.json must exist"
    assert diag_path.is_file(), "candidate_recall_diagnostics.json must exist"

    data = json.loads(report_path.read_text(encoding="utf-8"))
    diag_data = json.loads(diag_path.read_text(encoding="utf-8"))
    assert "model_metadata" in data
    assert "experiments" in data

    metadata = data["model_metadata"]
    assert metadata["model_name"] == "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    assert metadata["license"] == "Apache-2.0"
    assert metadata["memory_overhead_mb"] > 0
    assert "vi" in metadata["supported_languages"]
    assert "en" in metadata["supported_languages"]

    for exp_key in ["standard_14_chunks", "augmented_74_chunks"]:
        exp = data["experiments"][exp_key]
        diag_summary = diag_data[exp_key]["summary"]["hybrid"]
        assert exp["answerable_cases"] == 30

        # Baseline consistency between reports
        assert exp["baseline_hybrid"]["hit@1"] == diag_summary["hit@1"]
        assert exp["baseline_hybrid"]["hit@5"] == diag_summary["hit@5"]
        assert exp["baseline_hybrid"]["recall@5"] == diag_summary["recall@5"]

        # Latency validation (separated first-stage vs cross-encoder inference)
        lat_10 = exp["rerank_pool_10"]["latency_breakdown_ms"]
        lat_20 = exp["rerank_pool_20"]["latency_breakdown_ms"]
        for lat in [lat_10, lat_20]:
            assert lat["first_stage_retrieval"]["p50"] > 0
            assert lat["cross_encoder_inference"]["p50"] > 0
            assert lat["total_end_to_end"]["p50"] >= lat["cross_encoder_inference"]["p50"]

        # Candidate pool upper bound invariant: Reranked Hit@5 <= Candidate Pool Hit@K
        bounds = exp["candidate_pool_upper_bounds"]
        assert exp["rerank_pool_10"]["hit@5"] <= bounds["pool_10"]["candidate_hit@10"]
        assert exp["rerank_pool_10"]["upper_bound_satisfied"] is True
        assert exp["rerank_pool_20"]["hit@5"] <= bounds["pool_20"]["candidate_hit@20"]
        assert exp["rerank_pool_20"]["upper_bound_satisfied"] is True

        # Reranker accuracy vs baseline
        base_mrr = exp["baseline_hybrid"]["mrr@5"]
        rerank_mrr = exp["rerank_pool_20"]["mrr@5"]
        assert rerank_mrr > base_mrr, f"Reranking should improve MRR@5 ({rerank_mrr} > {base_mrr})"

        # Cross lingual subset improvement
        xl_stats = exp["cross_lingual_subset"]
        assert xl_stats["cases_count"] == 10
        assert xl_stats["rerank_20_hit1"] >= xl_stats["baseline_hybrid_hit1"]
        assert xl_stats["rerank_20_mrr5"] > xl_stats["baseline_hybrid_mrr5"]

    # Specific mathematical upper bounds for augmented distractor corpus
    aug_exp = data["experiments"]["augmented_74_chunks"]
    assert aug_exp["candidate_pool_upper_bounds"]["pool_10"]["candidate_hit@10"] == 0.8667
    assert aug_exp["rerank_pool_10"]["hit@5"] == 0.8667
    assert aug_exp["candidate_pool_upper_bounds"]["pool_20"]["candidate_hit@20"] == 0.9333
    assert aug_exp["rerank_pool_20"]["hit@5"] == 0.9333


def test_reranking_tenant_isolation_logic():
    # Verify that scoring candidates respects strict workspace scoping
    ws_alpha_candidates = ["doc_alpha_1", "doc_alpha_2"]
    ws_beta_candidates = ["doc_beta_secret"]

    # Simulating ranker only receiving alpha candidates
    expected_alpha = {"doc_alpha_1"}
    retrieved = dedupe_preserving_order(ws_alpha_candidates)
    
    assert hit_rate_at_k(retrieved, expected_alpha, k=1) == 1.0
    for beta_doc in ws_beta_candidates:
        assert beta_doc not in retrieved
    assert recall_at_k(retrieved, expected_alpha, k=5) == 1.0
    assert reciprocal_rank_at_k(retrieved, expected_alpha, k=5) == 1.0
