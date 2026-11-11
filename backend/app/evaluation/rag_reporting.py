"""Reporting and serialization for RAG quality evaluation (T260030).

Produces:
- Machine-readable JSON evaluation report.
- Executive Markdown summary with metric tables, category breakdowns,
  confusion matrix, and diagnostic failure drill-downs.
"""

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.embedding import EMBEDDING_MODEL_NAME
from app.evaluation.rag_dataset import Answerability, RAGDatasetManifest
from app.evaluation.rag_diagnostics import AnswerClassification, RAGCaseDiagnostic
from app.evaluation.rag_metrics import (
    empty_accepted_evidence_rate,
    empty_candidate_rate,
    empty_retrieval_rate,
    mean_reciprocal_rank,
    retrieval_coverage,
    tenant_isolation_rate,
)
from app.evaluation.rag_runner import EvaluationRunConfig


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _group_metrics(
    diags: list[RAGCaseDiagnostic],
    case_map: dict[str, Any],
) -> dict[str, Any]:
    """Metrics for one slice (category / language / tag).

    Answerable and refusal cases have separate denominators: retrieval quality metrics
    use answerable cases only, leak-free rate uses refusal cases only.
    """
    answerable = [
        d
        for d in diags
        if case_map[d.case_id].expected_answerability == Answerability.ANSWERABLE
    ]
    refusal = [d for d in diags if d not in answerable]
    passed = sum(1 for d in diags if d.passed)
    chunk_labeled = [d for d in answerable if d.chunk_labeled]
    return {
        "total": len(diags),
        "answerable": len(answerable),
        "refusal": len(refusal),
        "passed": passed,
        "pass_rate": round(passed / len(diags), 4) if diags else 0.0,
        "hit_rate_at_1": _mean([d.hit_at_1 for d in answerable]),
        "hit_rate_at_3": _mean([d.hit_at_3 for d in answerable]),
        "hit_rate_at_5": _mean([d.hit_at_5 for d in answerable]),
        "recall_at_1": _mean([d.recall_at_1 for d in answerable]),
        "recall_at_3": _mean([d.recall_at_3 for d in answerable]),
        "recall_at_5": _mean([d.recall_at_5 for d in answerable]),
        "precision_at_5": _mean([d.precision_at_5 for d in answerable]),
        "mrr_at_5": _mean([d.reciprocal_rank for d in answerable]),
        "chunk_labeled_cases": len(chunk_labeled),
        "chunk_recall_at_5": _mean([d.chunk_recall_at_5 for d in chunk_labeled]),
        "refusal_leak_free_rate": _mean(
            [
                1.0
                if (not d.negative_doc_retrieved and d.cross_tenant_chunks_count == 0)
                else 0.0
                for d in refusal
            ]
        ),
        "tenant_isolation_rate": _mean(
            [1.0 if d.cross_tenant_chunks_count == 0 else 0.0 for d in diags]
        ),
    }


def _breakdown(
    diagnostics: list[RAGCaseDiagnostic],
    case_map: dict[str, Any],
    key_fn: Any,
) -> dict[str, Any]:
    groups: dict[str, list[RAGCaseDiagnostic]] = {}
    for d in diagnostics:
        for key in key_fn(d):
            groups.setdefault(key, []).append(d)
    return {k: _group_metrics(v, case_map) for k, v in sorted(groups.items())}


def build_rag_quality_report(
    *,
    dataset: RAGDatasetManifest,
    diagnostics: list[RAGCaseDiagnostic],
    config: EvaluationRunConfig,
    llm_model_name: str | None = None,
    database_name: str | None = None,
    retrieval_strategy: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Aggregate per-case diagnostics into a comprehensive quality report."""
    total_cases = len(diagnostics)
    case_map = {c.case_id: c for c in dataset.cases}

    answerable_cases = [
        d
        for d in diagnostics
        if case_map[d.case_id].expected_answerability == Answerability.ANSWERABLE
    ]
    refusal_cases = [
        d
        for d in diagnostics
        if case_map[d.case_id].expected_answerability == Answerability.REFUSAL_REQUIRED
    ]

    # Retrieval metrics on answerable subset (where expected documents exist)
    if answerable_cases:
        mean_hit_1 = sum(d.hit_at_1 for d in answerable_cases) / len(answerable_cases)
        mean_hit_3 = sum(d.hit_at_3 for d in answerable_cases) / len(answerable_cases)
        mean_hit_5 = sum(d.hit_at_5 for d in answerable_cases) / len(answerable_cases)
        mean_rec_1 = sum(d.recall_at_1 for d in answerable_cases) / len(
            answerable_cases
        )
        mean_rec_3 = sum(d.recall_at_3 for d in answerable_cases) / len(
            answerable_cases
        )
        mean_rec_5 = sum(d.recall_at_5 for d in answerable_cases) / len(
            answerable_cases
        )
        mean_prec_1 = sum(d.precision_at_1 for d in answerable_cases) / len(
            answerable_cases
        )
        mean_prec_3 = sum(d.precision_at_3 for d in answerable_cases) / len(
            answerable_cases
        )
        mean_prec_5 = sum(d.precision_at_5 for d in answerable_cases) / len(
            answerable_cases
        )
        mrr = mean_reciprocal_rank([d.reciprocal_rank for d in answerable_cases])
        hits_list = [1 if d.recall_at_5 > 0 else 0 for d in answerable_cases]
        coverage = retrieval_coverage(hits_list)
    else:
        mean_hit_1 = mean_hit_3 = mean_hit_5 = 0.0
        mean_rec_1 = mean_rec_3 = mean_rec_5 = 0.0
        mean_prec_1 = mean_prec_3 = mean_prec_5 = 0.0
        mrr = coverage = 0.0

    chunk_labeled_cases = [d for d in answerable_cases if d.chunk_labeled]
    if chunk_labeled_cases:
        n_chunk = len(chunk_labeled_cases)
        chunk_rec_1 = sum(d.chunk_recall_at_1 for d in chunk_labeled_cases) / n_chunk
        chunk_rec_3 = sum(d.chunk_recall_at_3 for d in chunk_labeled_cases) / n_chunk
        chunk_rec_5 = sum(d.chunk_recall_at_5 for d in chunk_labeled_cases) / n_chunk
        chunk_extra: dict[str, float | None] = {
            "chunk_hit_rate_at_1": round(
                sum(d.chunk_hit_at_1 for d in chunk_labeled_cases) / n_chunk, 4
            ),
            "chunk_hit_rate_at_3": round(
                sum(d.chunk_hit_at_3 for d in chunk_labeled_cases) / n_chunk, 4
            ),
            "chunk_hit_rate_at_5": round(
                sum(d.chunk_hit_at_5 for d in chunk_labeled_cases) / n_chunk, 4
            ),
            "chunk_precision_at_5": round(
                sum(d.chunk_precision_at_5 for d in chunk_labeled_cases) / n_chunk, 4
            ),
            "chunk_mrr_at_5": round(
                sum(d.chunk_reciprocal_rank for d in chunk_labeled_cases) / n_chunk, 4
            ),
        }
    else:
        chunk_rec_1, chunk_rec_3, chunk_rec_5 = mean_rec_1, mean_rec_3, mean_rec_5
        chunk_extra = {
            "chunk_hit_rate_at_1": None,
            "chunk_hit_rate_at_3": None,
            "chunk_hit_rate_at_5": None,
            "chunk_precision_at_5": None,
            "chunk_mrr_at_5": None,
        }

    empty_rate = empty_retrieval_rate([d.retrieved_chunk_count for d in diagnostics])
    empty_cand_rate = empty_candidate_rate(
        [getattr(d, "candidates_count", d.retrieved_chunk_count) for d in diagnostics]
    )
    empty_evidence_rate = empty_accepted_evidence_rate(
        [
            getattr(d, "accepted_evidence_count", d.retrieved_chunk_count)
            for d in diagnostics
        ]
    )
    iso_rate = tenant_isolation_rate([d.cross_tenant_chunks_count for d in diagnostics])
    mean_retrieval_latency = (
        sum(d.retrieval_latency_ms for d in diagnostics) / total_cases
        if total_cases
        else 0.0
    )
    mean_embed_latency = (
        sum(getattr(d, "embedding_latency_ms", 0.0) for d in diagnostics) / total_cases
        if total_cases
        else 0.0
    )
    mean_vec_latency = (
        sum(
            getattr(d, "vector_latency_ms", d.retrieval_latency_ms) for d in diagnostics
        )
        / total_cases
        if total_cases
        else 0.0
    )
    mean_ctx_latency = (
        sum(getattr(d, "context_latency_ms", 0.0) for d in diagnostics) / total_cases
        if total_cases
        else 0.0
    )

    # Category breakdown
    categories = sorted({d.category for d in diagnostics})
    category_metrics: dict[str, Any] = {}
    for cat in categories:
        cat_diags = [d for d in diagnostics if d.category == cat]
        cat_answerable = [
            d
            for d in cat_diags
            if case_map[d.case_id].expected_answerability == Answerability.ANSWERABLE
        ]
        cat_passed = sum(1 for d in cat_diags if d.passed)
        cat_recall = (
            (sum(d.recall_at_5 for d in cat_answerable) / len(cat_answerable))
            if cat_answerable
            else None
        )
        category_metrics[cat] = {
            "total": len(cat_diags),
            "passed": cat_passed,
            "pass_rate": round(cat_passed / len(cat_diags), 4),
            "mean_recall_at_5": round(cat_recall, 4)
            if cat_recall is not None
            else "N/A (Refusal)",
            **{
                k: v
                for k, v in _group_metrics(cat_diags, case_map).items()
                if k not in ("total", "passed", "pass_rate")
            },
        }

    report: dict[str, Any] = {
        "metadata": {
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "execution_mode": config.mode,
            "retrieval_strategy": retrieval_strategy or "unspecified",
            "chunk_labeled_cases_count": len(chunk_labeled_cases),
            "chunk_metrics_scope": (
                "chunk-labeled answerable cases only"
                if chunk_labeled_cases
                else "no chunk labels: chunk_recall mirrors doc recall (1 chunk/doc corpus)"
            ),
            "database_environment": database_name or "isolated synthetic fixture",
            "embedding_model": EMBEDDING_MODEL_NAME,
            "llm_model": llm_model_name
            or (
                "None (retrieval-only)"
                if config.mode
                in ("retrieval-only", "synthetic-in-memory", "real-pgvector")
                else "qwen3:1.7b"
            ),
            "k": config.k,
            "total_cases": total_cases,
            "answerable_cases_count": len(answerable_cases),
            "refusal_cases_count": len(refusal_cases),
        },
        "retrieval_metrics": {
            "hit_rate_at_1": round(mean_hit_1, 4),
            "hit_rate_at_3": round(mean_hit_3, 4),
            "hit_rate_at_5": round(mean_hit_5, 4),
            "recall_at_1": round(mean_rec_1, 4),
            "recall_at_3": round(mean_rec_3, 4),
            "recall_at_5": round(mean_rec_5, 4),
            "doc_recall_at_1": round(mean_rec_1, 4),
            "doc_recall_at_3": round(mean_rec_3, 4),
            "doc_recall_at_5": round(mean_rec_5, 4),
            "chunk_recall_at_1": round(chunk_rec_1, 4),
            "chunk_recall_at_3": round(chunk_rec_3, 4),
            "chunk_recall_at_5": round(chunk_rec_5, 4),
            **chunk_extra,
            "precision_at_1": round(mean_prec_1, 4),
            "precision_at_3": round(mean_prec_3, 4),
            "precision_at_5": round(mean_prec_5, 4),
            "mrr_at_5": round(mrr, 4),
            "retrieval_coverage": round(coverage, 4),
            "empty_retrieval_rate": round(empty_rate, 4),
            "empty_candidate_rate": round(empty_cand_rate, 4),
            "empty_accepted_evidence_rate": round(empty_evidence_rate, 4),
            "tenant_isolation_rate": round(iso_rate, 4),
            "mean_latency_ms": round(mean_retrieval_latency, 2),
            "mean_embedding_latency_ms": round(mean_embed_latency, 2),
            "mean_vector_latency_ms": round(mean_vec_latency, 2),
            "mean_context_latency_ms": round(mean_ctx_latency, 2),
        },
        "category_breakdown": category_metrics,
        "language_breakdown": _breakdown(
            diagnostics, case_map, lambda d: [case_map[d.case_id].language]
        ),
        "tag_breakdown": _breakdown(
            diagnostics, case_map, lambda d: case_map[d.case_id].tags
        ),
        "refusal_metrics": {
            "refusal_cases": len(refusal_cases),
            "leak_free_rate": _group_metrics(refusal_cases, case_map)[
                "refusal_leak_free_rate"
            ]
            if refusal_cases
            else None,
            "note": (
                "Retrieval-level refusal check only: a refusal case passes when no "
                "cross-tenant or negative document is retrieved. Generation-level "
                "correct refusal requires full-rag mode."
            ),
        },
        "cases": [
            {
                "case_id": d.case_id,
                "query": d.query,
                "language": case_map[d.case_id].language,
                "tags": list(case_map[d.case_id].tags),
                "expected_documents": list(case_map[d.case_id].expected_document_keys),
                "expected_chunk_ids": list(case_map[d.case_id].expected_chunk_ids),
                "first_relevant_doc_rank": d.first_relevant_doc_rank,
                "first_relevant_chunk_rank": d.first_relevant_chunk_rank,
                "chunk_labeled": d.chunk_labeled,
                "retrieved_chunk_ids": list(d.retrieved_chunk_ids),
                "retrieval_provenance": list(d.retrieval_provenance),
                "category": d.category,
                "difficulty": d.difficulty,
                "workspace_ref": d.workspace_ref,
                "passed": d.passed,
                "hit_at_1": d.hit_at_1,
                "hit_at_5": d.hit_at_5,
                "recall_at_5": d.recall_at_5,
                "doc_recall_at_5": getattr(d, "doc_recall_at_5", d.recall_at_5),
                "chunk_recall_at_5": getattr(d, "chunk_recall_at_5", d.recall_at_5),
                "precision_at_5": d.precision_at_5,
                "reciprocal_rank": d.reciprocal_rank,
                "candidates_count": getattr(
                    d, "candidates_count", d.retrieved_chunk_count
                ),
                "accepted_evidence_count": getattr(
                    d, "accepted_evidence_count", d.retrieved_chunk_count
                ),
                "filtered_chunks_count": getattr(d, "filtered_chunks_count", 0),
                "retrieved_keys": list(d.retrieved_doc_keys),
                "similarity_scores": list(d.similarity_scores),
                "cross_tenant_chunks": d.cross_tenant_chunks_count,
                "classification": d.classification.value
                if hasattr(d.classification, "value")
                else str(d.classification),
                "root_cause": d.root_cause.value
                if hasattr(d.root_cause, "value")
                else str(d.root_cause),
                "notes": d.notes,
                "retrieval_latency_ms": d.retrieval_latency_ms,
                "embedding_latency_ms": getattr(d, "embedding_latency_ms", 0.0),
                "vector_latency_ms": getattr(
                    d, "vector_latency_ms", d.retrieval_latency_ms
                ),
                "context_latency_ms": getattr(d, "context_latency_ms", 0.0),
                "generation_latency_ms": d.generation_latency_ms,
            }
            for d in diagnostics
        ],
    }

    # Add generation quality metrics if full-rag mode
    if config.mode == "full-rag":
        class_counts = Counter(d.classification.value for d in diagnostics)
        root_causes = Counter(d.root_cause.value for d in diagnostics)

        correct_answers = class_counts.get(AnswerClassification.CORRECT_ANSWER.value, 0)
        correct_refusals = class_counts.get(
            AnswerClassification.CORRECT_REFUSAL.value, 0
        )
        false_refusals = class_counts.get(AnswerClassification.FALSE_REFUSAL.value, 0)
        unsupported = class_counts.get(AnswerClassification.UNSUPPORTED_ANSWER.value, 0)

        ans_count = len(answerable_cases) or 1
        ref_count = len(refusal_cases) or 1

        accuracy_rate = correct_answers / ans_count
        correct_refusal_rate = correct_refusals / ref_count
        false_refusal_rate = false_refusals / ans_count
        overall_pass_rate = (
            sum(1 for d in diagnostics if d.passed) / total_cases
            if total_cases
            else 0.0
        )

        mean_gen_latency = (
            sum(d.generation_latency_ms for d in diagnostics) / total_cases
            if total_cases
            else 0.0
        )

        report["generation_metrics"] = {
            "overall_pass_rate": round(overall_pass_rate, 4),
            "accuracy_rate": round(accuracy_rate, 4),
            "correct_refusal_rate": round(correct_refusal_rate, 4),
            "false_refusal_rate": round(false_refusal_rate, 4),
            "unsupported_answer_rate": round(unsupported / total_cases, 4),
            "mean_generation_latency_ms": round(mean_gen_latency, 2),
            "classification_breakdown": dict(class_counts),
            "failure_root_causes": dict(root_causes),
        }

    return report


def render_rag_evaluation_markdown(report: dict[str, Any]) -> str:
    """Render a GitHub-flavored Markdown evaluation summary report."""
    meta = report["metadata"]
    ret = report["retrieval_metrics"]
    gen = report.get("generation_metrics")

    lines = [
        f"# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG & TRUY VẤN NGỮ NGHĨA ({meta['dataset_id'].upper()})",
        "",
        f"- **Phiên bản Dataset:** `{meta['dataset_version']}`",
        f"- **Thời điểm đánh giá:** `{meta['timestamp']}`",
        f"- **Chế độ thực thi:** `{meta['execution_mode']}`",
        f"- **Chiến lược truy xuất:** `{meta.get('retrieval_strategy', 'unspecified')}`",
        f"- **Môi trường CSDL:** `{meta.get('database_environment', 'isolated test DB')}`",
        f"- **Mô hình nhúng (Embedding):** `{meta['embedding_model']}` (384 dims)",
        f"- **Mô hình LLM:** `{meta['llm_model']}`",
        f"- **Tổng số ca kiểm thử:** **{meta['total_cases']}** ({meta['answerable_cases_count']} câu có đáp án, {meta['refusal_cases_count']} câu yêu cầu từ chối)",
        "",
        "---",
        "",
        "## 1. CHỈ SỐ TRUY XUẤT NGỮ NGHĨA (RETRIEVAL METRICS)",
        "",
        "| Chỉ số đo lường | Giá trị | Định nghĩa toán học & Mẫu số | Đánh giá |",
        "| :--- | :---: | :--- | :---: |",
        f"| **Hit Rate@1** | `{ret.get('hit_rate_at_1', ret['recall_at_1']) * 100:.1f}%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-1 (mẫu số: {meta['answerable_cases_count']} ca) | {'Rất tốt' if ret.get('hit_rate_at_1', 0) > 0.8 else 'Khá'} |",
        f"| **Hit Rate@3** | `{ret.get('hit_rate_at_3', ret['recall_at_3']) * 100:.1f}%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-3 (mẫu số: {meta['answerable_cases_count']} ca) | {'Xuất sắc' if ret.get('hit_rate_at_3', 0) > 0.9 else 'Khá'} |",
        f"| **Hit Rate@5** | `{ret.get('hit_rate_at_5', ret['recall_at_5']) * 100:.1f}%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-5 (mẫu số: {meta['answerable_cases_count']} ca) | {'Xuất sắc' if ret.get('hit_rate_at_5', 0) > 0.9 else 'Khá'} |",
        rf"| **Recall@1 (Doc-level)** | `{ret['recall_at_1'] * 100:.1f}%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Tốt' if ret['recall_at_1'] > 0.7 else 'Cần tối ưu'} |",
        rf"| **Recall@3 (Doc-level)** | `{ret['recall_at_3'] * 100:.1f}%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Rất tốt' if ret['recall_at_3'] > 0.85 else 'Trung bình'} |",
        rf"| **Recall@5 (Doc-level)** | `{ret['recall_at_5'] * 100:.1f}%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Xuất sắc' if ret['recall_at_5'] > 0.9 else 'Đạt yêu cầu'} |",
        rf"| **Chunk-level Recall@5** | `{ret.get('chunk_recall_at_5', ret['recall_at_5']) * 100:.1f}%` | Tỷ lệ chunk liên quan kỳ vọng được tìm thấy trong Top-5 | {'Xuất sắc' if ret.get('chunk_recall_at_5', ret['recall_at_5']) > 0.9 else 'Đạt'} |",
        rf"| **Precision@5** | `{ret['precision_at_5'] * 100:.1f}%` | \|Top-5 ∩ Expected\| / 5 (trần lý thuyết = số tài liệu kỳ vọng / 5) | Mật độ trong Top-5 |",
        rf"| **Mean Reciprocal Rank (MRR@5)** | `{ret['mrr_at_5']:.4f}` | 1/\|Q\| * Σ (1/Rank_1) = {ret['mrr_at_5'] * meta['answerable_cases_count']:.4f} / {meta['answerable_cases_count']} | {'Rất cao' if ret['mrr_at_5'] > 0.8 else 'Khá'} |",
        f"| **Retrieval Coverage** | `{ret['retrieval_coverage'] * 100:.1f}%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | {'Toàn diện' if ret['retrieval_coverage'] > 0.9 else 'Cần chú ý'} |",
        f"| **Empty Retrieval Rate** | `{ret['empty_retrieval_rate'] * 100:.1f}%` | Tỷ lệ truy vấn trả về 0 chunk | Lý tưởng |",
        f"| **Empty Candidate Rate** | `{ret.get('empty_candidate_rate', ret['empty_retrieval_rate']) * 100:.1f}%` | Tỷ lệ truy vấn có 0 ứng viên từ tìm kiếm vector | Lý tưởng |",
        f"| **Empty Accepted Evidence Rate** | `{ret.get('empty_accepted_evidence_rate', ret['empty_retrieval_rate']) * 100:.1f}%` | Tỷ lệ truy vấn không có chunk nào đủ điều kiện vào context | Lý tưởng |",
        f"| **Tenant Isolation Rate** | `{ret['tenant_isolation_rate'] * 100:.1f}%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace | **BẢO MẬT TUYỆT ĐỐI (100%)** |",
        f"| **Độ trễ trung bình truy xuất** | `{ret['mean_latency_ms']:.2f} ms` | Tổng thời gian nhúng câu hỏi + truy vấn vector | {'Siêu tốc' if ret['mean_latency_ms'] < 100 else 'Bình thường'} |",
        f"| - *Độ trễ nhúng câu hỏi (Embedding)* | `{ret.get('mean_embedding_latency_ms', 0.0):.2f} ms` | Thời gian tính vector câu hỏi qua multilingual-e5-small | Dense Model |",
        f"| - *Độ trễ truy vấn vector (pgvector)* | `{ret.get('mean_vector_latency_ms', ret['mean_latency_ms']):.2f} ms` | Thời gian quét pgvector HNSW cosine_distance trong CSDL | Live Database |",
        f"| - *Độ trễ lắp ráp ngữ cảnh (Context)* | `{ret.get('mean_context_latency_ms', 0.0):.2f} ms` | Thời gian lọc ký tự và tạo block [Source N] | Prompt Assembly |",
        "",
        "---",
        "",
        "## 2. PHÂN TÍCH THEO NHÓM KIỂM THỬ (CATEGORY BREAKDOWN)",
        "",
        "| Phân loại kiểm thử | Số ca | Số ca đạt | Tỷ lệ đạt | Recall@5 trung bình |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for cat, data in report["category_breakdown"].items():
        rec_str = (
            f"{data['mean_recall_at_5'] * 100:.1f}%"
            if isinstance(data["mean_recall_at_5"], (int, float))
            else str(data["mean_recall_at_5"])
        )
        lines.append(
            f"| `{cat}` | {data['total']} | {data['passed']} | **{data['pass_rate'] * 100:.1f}%** | {rec_str} |"
        )

    def _pct(value: Any) -> str:
        return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "N/A"

    for title, key in (
        ("PHÂN TÍCH THEO NGÔN NGỮ TRUY VẤN (LANGUAGE BREAKDOWN)", "language_breakdown"),
        ("PHÂN TÍCH THEO THẺ KỊCH BẢN (TAG BREAKDOWN)", "tag_breakdown"),
    ):
        groups = report.get(key) or {}
        if not groups:
            continue
        lines.extend(
            [
                "",
                f"### {title}",
                "",
                "| Nhóm | Số ca | Có đáp án | Hit@1 | Hit@5 | Recall@5 | MRR@5 |",
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
            ]
        )
        for name, g in groups.items():
            lines.append(
                f"| `{name}` | {g['total']} | {g['answerable']} | {_pct(g['hit_rate_at_1'])} "
                f"| {_pct(g['hit_rate_at_5'])} | {_pct(g['recall_at_5'])} "
                f"| {g['mrr_at_5'] if g['mrr_at_5'] is not None else 'N/A'} |"
            )

    if gen:
        lines.extend(
            [
                "",
                "---",
                "",
                "## 3. CHỈ SỐ CHẤT LƯỢNG SINH CÂU TRẢ LỜI & BỘ LỌC TỪ CHỐI (FULL-RAG METRICS)",
                "",
                "| Chỉ số chất lượng | Giá trị | Ý nghĩa kỹ thuật |",
                "| :--- | :---: | :--- |",
                f"| **Tỷ lệ vượt qua tổng thể (Overall Pass Rate)** | **`{gen['overall_pass_rate'] * 100:.1f}%`** | Toàn bộ các tiêu chí (đúng fact, đúng trích dẫn, từ chối chuẩn) |",
                f"| **Độ chính xác câu trả lời (Accuracy Rate)** | `{gen['accuracy_rate'] * 100:.1f}%` | Câu trả lời đúng sự thật trên các câu hỏi có đáp án |",
                f"| **Từ chối chính xác (Correct Refusal Rate)** | `{gen['correct_refusal_rate'] * 100:.1f}%` | Hệ thống từ chối thành công khi thiếu dữ liệu / vi phạm tenant |",
                f"| **Từ chối nhầm (False Refusal Rate)** | `{gen['false_refusal_rate'] * 100:.1f}%` | Tỷ lệ từ chối sai khi dữ liệu nguồn thực sự có sẵn |",
                f"| **Câu trả lời không căn cứ (Unsupported Rate)** | `{gen['unsupported_answer_rate'] * 100:.1f}%` | Câu trả lời thiếu hoặc trích dẫn nguồn không hợp lệ |",
                f"| **Độ trễ sinh câu trả lời trung bình** | `{gen['mean_generation_latency_ms']:.2f} ms` | Thời gian suy luận LLM |",
                "",
                "### Bảng phân phối phân loại phản hồi (Classification Breakdown):",
                "",
            ]
        )
        for cls_name, count in gen["classification_breakdown"].items():
            lines.append(f"- **`{cls_name}`**: {count} ca")

        lines.extend(
            [
                "",
                "### Nguyên nhân thất bại (Failure Root Causes):",
                "",
            ]
        )
        for cause_name, count in gen["failure_root_causes"].items():
            lines.append(f"- **`{cause_name}`**: {count} ca")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. CHI TIẾT CÁC CA KIỂM THỬ KHÔNG ĐẠT (FAILED CASES DIAGNOSTICS)",
            "",
        ]
    )

    failed_cases = [c for c in report["cases"] if not c["passed"]]
    if not failed_cases:
        lines.append(
            "🎉 **Tất cả các ca kiểm chuẩn đều đạt tiêu chuẩn chất lượng (100% PASS)! Không có lỗi suy diễn hay truy xuất thất bại.**"
        )
    else:
        for fc in failed_cases:
            lines.extend(
                [
                    f"### ❌ Case ID: `{fc['case_id']}` ({fc['category']})",
                    f"- **Workspace:** `{fc['workspace_ref']}` | **Difficulty:** `{fc['difficulty']}`",
                    f"- **Recall@5:** `{fc['recall_at_5']}` | **Precision@5:** `{fc['precision_at_5']}`",
                    f"- **Retrieved Document Keys:** `{fc['retrieved_keys']}`",
                    f"- **Classification:** `{fc['classification']}`",
                    f"- **Root Cause:** `{fc['root_cause']}`",
                    f"- **Ghi chú lỗi:** {fc['notes']}",
                    "",
                ]
            )

    return "\n".join(lines)
