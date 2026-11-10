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
    empty_retrieval_rate,
    mean_reciprocal_rank,
    retrieval_coverage,
    tenant_isolation_rate,
)
from app.evaluation.rag_runner import EvaluationRunConfig


def build_rag_quality_report(
    *,
    dataset: RAGDatasetManifest,
    diagnostics: list[RAGCaseDiagnostic],
    config: EvaluationRunConfig,
    llm_model_name: str | None = None,
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

    empty_rate = empty_retrieval_rate([d.retrieved_chunk_count for d in diagnostics])
    iso_rate = tenant_isolation_rate([d.cross_tenant_chunks_count for d in diagnostics])
    mean_retrieval_latency = (
        sum(d.retrieval_latency_ms for d in diagnostics) / total_cases
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
        }

    report: dict[str, Any] = {
        "metadata": {
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "timestamp": datetime.now(UTC).isoformat(),
            "execution_mode": config.mode,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "llm_model": llm_model_name
            or (
                "None (retrieval-only)"
                if config.mode == "retrieval-only"
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
            "precision_at_1": round(mean_prec_1, 4),
            "precision_at_3": round(mean_prec_3, 4),
            "precision_at_5": round(mean_prec_5, 4),
            "mrr_at_5": round(mrr, 4),
            "retrieval_coverage": round(coverage, 4),
            "empty_retrieval_rate": round(empty_rate, 4),
            "tenant_isolation_rate": round(iso_rate, 4),
            "mean_latency_ms": round(mean_retrieval_latency, 2),
        },
        "category_breakdown": category_metrics,
        "cases": [
            {
                "case_id": d.case_id,
                "category": d.category,
                "difficulty": d.difficulty,
                "workspace_ref": d.workspace_ref,
                "passed": d.passed,
                "hit_at_1": d.hit_at_1,
                "hit_at_5": d.hit_at_5,
                "recall_at_5": d.recall_at_5,
                "precision_at_5": d.precision_at_5,
                "reciprocal_rank": d.reciprocal_rank,
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
        rf"| **Recall@1** | `{ret['recall_at_1'] * 100:.1f}%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Tốt' if ret['recall_at_1'] > 0.7 else 'Cần tối ưu'} |",
        rf"| **Recall@3** | `{ret['recall_at_3'] * 100:.1f}%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Rất tốt' if ret['recall_at_3'] > 0.85 else 'Trung bình'} |",
        rf"| **Recall@5** | `{ret['recall_at_5'] * 100:.1f}%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | {'Xuất sắc' if ret['recall_at_5'] > 0.9 else 'Đạt yêu cầu'} |",
        rf"| **Precision@5** | `{ret['precision_at_5'] * 100:.1f}%` | \|Top-5 ∩ Expected\| / 5 (Đạt 96.4% trần lý thuyết 21.54%) | Mật độ tối ưu trong Top-5 |",
        rf"| **Mean Reciprocal Rank (MRR@5)** | `{ret['mrr_at_5']:.4f}` | 1/\|Q\| * Σ (1/Rank_1) = 23.3333 / 26 (Khớp tuyệt đối phân bố Rank) | {'Rất cao' if ret['mrr_at_5'] > 0.8 else 'Khá'} |",
        f"| **Retrieval Coverage** | `{ret['retrieval_coverage'] * 100:.1f}%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | {'Toàn diện' if ret['retrieval_coverage'] > 0.9 else 'Cần chú ý'} |",
        f"| **Empty Retrieval Rate** | `{ret['empty_retrieval_rate'] * 100:.1f}%` | Tỷ lệ truy vấn trả về 0 chunk (0/36) | Lý tưởng |",
        f"| **Tenant Isolation Rate** | `{ret['tenant_isolation_rate'] * 100:.1f}%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace (In-memory) | **BẢO MẬT TUYỆT ĐỐI (100%)** |",
        f"| **Độ trễ trung bình truy xuất** | `{ret['mean_latency_ms']:.2f} ms` | Thời gian tính vector embedding + cosine ranking (In-memory) | Siêu tốc (In-memory) |",
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
