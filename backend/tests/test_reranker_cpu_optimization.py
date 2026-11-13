"""Tests for CPU Reranker Optimization & Reproducible Benchmarking (Task T260037)."""

import json
from pathlib import Path

import pytest

from app.evaluation.reranker_benchmark import calculate_ranking_parity

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "datasets/evaluation/reports/reranker_cpu_benchmark_report.json"
MODELS_DIR = REPO_ROOT.parent / "storage/models/reranker"


def test_reranker_onnx_artifacts_integrity():
    """Verify exported ONNX FP32 and INT8 artifacts exist and meet compression requirements."""
    fp32_path = MODELS_DIR / "model_fp32.onnx"
    int8_path = MODELS_DIR / "model_int8.onnx"

    assert fp32_path.is_file(), f"ONNX FP32 model missing at {fp32_path}"
    assert int8_path.is_file(), f"ONNX INT8 model missing at {int8_path}"

    fp32_size_mb = fp32_path.stat().st_size / (1024 * 1024)
    int8_size_mb = int8_path.stat().st_size / (1024 * 1024)

    assert 400.0 <= fp32_size_mb <= 500.0, f"Unexpected FP32 size: {fp32_size_mb:.2f} MB"
    assert 90.0 <= int8_size_mb <= 140.0, f"Unexpected INT8 size: {int8_size_mb:.2f} MB"

    compression_ratio = fp32_size_mb / int8_size_mb
    assert compression_ratio >= 3.5, f"Compression ratio {compression_ratio:.2f}x is below expected 3.5x"


def test_cpu_reranker_benchmark_report_structure():
    """Verify benchmark report structure, metadata, and required sections."""
    assert REPORT_PATH.is_file(), f"Report file missing at {REPORT_PATH}"
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    metadata = report.get("metadata", {})
    assert metadata.get("task_id") == "T260037"
    assert metadata.get("benchmark_passes") == 5
    assert metadata.get("intra_op_threads") == 4
    assert metadata.get("corpus", {}).get("total_chunks") == 74
    assert metadata.get("corpus", {}).get("answerable_queries") == 30

    cpu_hardware = metadata.get("cpu_hardware", {})
    assert "model_name" in cpu_hardware
    assert cpu_hardware.get("has_avx2") is True

    # Check sections
    assert "first_stage_retrieval" in report
    assert "variants" in report
    assert "parity_analysis" in report
    assert "speedups" in report
    assert "decision_matrix" in report
    assert "recommendation" in report

    variants = report["variants"]
    assert "PyTorch_FP32" in variants
    assert "ONNX_FP32" in variants
    assert "ONNX_INT8" in variants


def test_candidate_pool_upper_bounds_invariant():
    """Mathematical invariant: Reranked Hit@5 <= Candidate Pool Hit@K and Recall@5 <= Recall@K."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    cand_bounds = report["first_stage_retrieval"]["candidate_upper_bounds"]
    pool_10_bound_hit = cand_bounds["pool_10"]["candidate_hit@10"]
    pool_10_bound_rec = cand_bounds["pool_10"]["candidate_recall@10"]
    pool_20_bound_hit = cand_bounds["pool_20"]["candidate_hit@20"]
    pool_20_bound_rec = cand_bounds["pool_20"]["candidate_recall@20"]

    for var_name, var_data in report["variants"].items():
        # Pool 10
        p10 = var_data["pools"]["pool_10"]["accuracy"]
        assert p10["hit@5"] <= pool_10_bound_hit, (
            f"Invariant violation in {var_name} Pool-10: Hit@5 ({p10['hit@5']}) > Bound ({pool_10_bound_hit})"
        )
        assert p10["recall@5"] <= pool_10_bound_rec + 1e-4, (
            f"Invariant violation in {var_name} Pool-10: Recall@5 ({p10['recall@5']}) > Bound ({pool_10_bound_rec})"
        )
        assert p10["upper_bound_satisfied"] is True

        # Pool 20
        p20 = var_data["pools"]["pool_20"]["accuracy"]
        assert p20["hit@5"] <= pool_20_bound_hit, (
            f"Invariant violation in {var_name} Pool-20: Hit@5 ({p20['hit@5']}) > Bound ({pool_20_bound_hit})"
        )
        assert p20["recall@5"] <= pool_20_bound_rec + 1e-4, (
            f"Invariant violation in {var_name} Pool-20: Recall@5 ({p20['recall@5']}) > Bound ({pool_20_bound_rec})"
        )
        assert p20["upper_bound_satisfied"] is True


def test_numerical_and_ranking_parity():
    """Verify parity between PyTorch FP32 and ONNX FP32 / INT8."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    parity = report["parity_analysis"]

    # ONNX FP32 vs PyTorch FP32 must be virtually identical
    fp32_p10 = parity["ONNX_FP32_vs_PyTorch"]["pool_10"]
    fp32_p20 = parity["ONNX_FP32_vs_PyTorch"]["pool_20"]
    assert fp32_p10["top1_exact_agreement_pct"] == 100.0
    assert fp32_p20["top1_exact_agreement_pct"] == 100.0
    assert fp32_p10["ground_truth_rank_agreement_pct"] == 100.0
    assert fp32_p20["ground_truth_rank_agreement_pct"] == 100.0
    assert fp32_p10["top5_membership_agreement_pct"] == 100.0
    assert fp32_p20["top5_membership_agreement_pct"] == 100.0
    assert fp32_p10["mean_spearman_rank_correlation"] >= 0.999
    assert fp32_p20["mean_spearman_rank_correlation"] >= 0.999
    assert fp32_p10["mean_absolute_error_logits"] < 1e-4
    assert fp32_p20["mean_absolute_error_logits"] < 1e-4

    # ONNX INT8 vs PyTorch FP32 must preserve high correlation and bounds
    int8_p10 = parity["ONNX_INT8_vs_PyTorch"]["pool_10"]
    int8_p20 = parity["ONNX_INT8_vs_PyTorch"]["pool_20"]
    assert int8_p10["top1_exact_agreement_pct"] >= 80.0
    assert int8_p20["top1_exact_agreement_pct"] >= 80.0
    assert int8_p10["ground_truth_rank_agreement_pct"] >= 90.0
    assert int8_p20["ground_truth_rank_agreement_pct"] >= 90.0
    assert int8_p10["mean_spearman_rank_correlation"] >= 0.80
    assert int8_p20["mean_spearman_rank_correlation"] >= 0.80
    assert int8_p10["mean_pearson_correlation"] >= 0.95
    assert int8_p20["mean_pearson_correlation"] >= 0.95
    assert int8_p10["top5_membership_agreement_pct"] == 100.0
    assert int8_p20["top5_membership_agreement_pct"] == 100.0


def test_ranking_parity_swaps_and_monotonicity():
    """Verify that rank swaps proportionally decrease Spearman correlation without breaking metrics."""
    base = [5.0, 4.0, 3.0, 2.0, 1.0]

    # Perfect identical order
    res_identical = calculate_ranking_parity(base, [10.0, 8.0, 6.0, 4.0, 2.0])
    assert res_identical["spearman"] == 1.0
    assert res_identical["pearson"] == 1.0
    assert res_identical["top1_match"] == 1.0

    # Single swap of adjacent items at bottom
    res_swap_bottom = calculate_ranking_parity(base, [5.0, 4.0, 3.0, 1.0, 2.0])
    assert 0.8 <= res_swap_bottom["spearman"] < 1.0
    assert res_swap_bottom["top1_match"] == 1.0

    # Swap of top item
    res_swap_top = calculate_ranking_parity(base, [4.0, 5.0, 3.0, 2.0, 1.0])
    assert 0.8 <= res_swap_top["spearman"] < 1.0
    assert res_swap_top["top1_match"] == 0.0

    # Complete reversal
    res_reverse = calculate_ranking_parity(base, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert res_reverse["spearman"] == -1.0
    assert res_reverse["top1_match"] == 0.0


def test_ranking_parity_ties_handling():
    """Verify handling of tied scores and constant vectors."""
    # Constant vectors
    res_const = calculate_ranking_parity([2.0, 2.0, 2.0], [2.0, 2.0, 2.0])
    assert res_const["spearman"] == 1.0
    assert res_const["pearson"] == 1.0
    assert res_const["top1_match"] == 1.0

    # Partial ties
    res_ties = calculate_ranking_parity([3.0, 2.0, 2.0, 1.0], [3.0, 2.0, 2.0, 1.0])
    assert res_ties["spearman"] == 1.0
    assert res_ties["pearson"] == 1.0
    assert res_ties["top1_match"] == 1.0


def test_ranking_parity_unequal_sets_raises_error():
    """Unequal candidate sets must raise explicit ValueError."""
    with pytest.raises(ValueError, match="Unequal candidate sets"):
        calculate_ranking_parity([1.0, 2.0, 3.0], [1.0, 2.0])


def test_cross_lingual_mrr_calculation():
    """Verify that MRR@5 on the 10 cross-lingual queries is isolated and not polluted by global MRR."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    global_mrr_p10 = report["variants"]["PyTorch_FP32"]["pools"]["pool_10"]["accuracy"]["mrr@5"]
    global_mrr_p20 = report["variants"]["PyTorch_FP32"]["pools"]["pool_20"]["accuracy"]["mrr@5"]

    for var_name, var_data in report["variants"].items():
        xl_10 = var_data["pools"]["pool_10"]["subsets"]["cross_lingual"]
        xl_20 = var_data["pools"]["pool_20"]["subsets"]["cross_lingual"]

        assert xl_10["count"] == 10
        assert xl_20["count"] == 10

        # Subsets must not accidentally mirror global accuracy
        assert xl_10["mrr@5"] != global_mrr_p10
        assert xl_20["mrr@5"] != global_mrr_p20

        # Specific verified values
        if var_name in ("PyTorch_FP32", "ONNX_FP32"):
            assert xl_10["mrr@5"] == 0.65
            assert xl_20["mrr@5"] == 0.85
        elif var_name == "ONNX_INT8":
            assert xl_10["mrr@5"] == 0.65
            assert xl_20["mrr@5"] == 0.80  # H-XL-08 shifted from rank 1 to rank 2


def test_onnx_int8_cpu_latency_tradeoffs():
    """Verify that ONNX INT8 achieves speedup on Pool-10 but does not outperform PyTorch on Pool-20 on this hardware."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    pt_p10 = report["variants"]["PyTorch_FP32"]["pools"]["pool_10"]["latency_breakdown_ms"]["reranker_total"]["p50"]
    int8_p10 = report["variants"]["ONNX_INT8"]["pools"]["pool_10"]["latency_breakdown_ms"]["reranker_total"]["p50"]
    assert int8_p10 < pt_p10, f"INT8 should be faster on Pool-10 ({int8_p10} < {pt_p10})"

    pt_p20 = report["variants"]["PyTorch_FP32"]["pools"]["pool_20"]["latency_breakdown_ms"]["reranker_total"]["p50"]
    int8_p20 = report["variants"]["ONNX_INT8"]["pools"]["pool_20"]["latency_breakdown_ms"]["reranker_total"]["p50"]
    # Explicit architectural finding: INT8 does not outperform PyTorch on Pool-20 without AVX-512
    assert int8_p20 >= pt_p20, f"INT8 on Pool-20 does not outperform PyTorch FP32 on AVX2 hardware ({int8_p20} >= {pt_p20})"


def test_exact_identifier_preservation():
    """Exact identifier queries must maintain 100% Hit@1 across all variants."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    for var_name, var_data in report["variants"].items():
        id_subset_10 = var_data["pools"]["pool_10"]["subsets"]["exact_identifier"]
        id_subset_20 = var_data["pools"]["pool_20"]["subsets"]["exact_identifier"]

        assert id_subset_10["count"] == 6
        assert id_subset_20["count"] == 6
        assert id_subset_10["hit@1"] == 1.0, f"{var_name} failed exact identifier Hit@1 in Pool-10"
        assert id_subset_20["hit@1"] == 1.0, f"{var_name} failed exact identifier Hit@1 in Pool-20"


def test_cross_lingual_improvement():
    """Reranker variants must significantly improve Cross-Lingual MRR@5 over baseline Hybrid."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    baseline_mrr = report["first_stage_retrieval"]["baseline_hybrid"]["mrr@5"]

    for var_name, var_data in report["variants"].items():
        xl_p20 = var_data["pools"]["pool_20"]["subsets"]["cross_lingual"]
        assert xl_p20["count"] == 10
        assert xl_p20["mrr@5"] > baseline_mrr, (
            f"{var_name} cross-lingual MRR@5 ({xl_p20['mrr@5']}) not higher than baseline ({baseline_mrr})"
        )


def test_decision_matrix_and_recommendation():
    """Verify decision matrix completeness and final recommendation."""
    assert REPORT_PATH.is_file()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    dm = report["decision_matrix"]
    assert "PyTorch_FP32" in dm
    assert "ONNX_FP32" in dm
    assert "ONNX_INT8" in dm

    rec = report["recommendation"]
    assert rec["recommended_variant"] == "ONNX_INT8"
    assert rec["production_readiness"] == "OFFLINE_FEASIBILITY_VERIFIED_CANDIDATE_READY"
    assert "rationale" in rec
    assert "caveat" in rec
