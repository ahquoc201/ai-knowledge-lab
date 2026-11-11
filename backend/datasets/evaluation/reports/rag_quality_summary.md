# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG & TRUY VẤN NGỮ NGHĨA (AI-KNOWLEDGE-LAB-RAG-QUALITY)

- **Phiên bản Dataset:** `2.0`
- **Thời điểm đánh giá:** `2026-11-11T02:48:42.438541+00:00`
- **Chế độ thực thi:** `retrieval-only`
- **Môi trường CSDL:** `ailab_eval_test`
- **Mô hình nhúng (Embedding):** `intfloat/multilingual-e5-small` (384 dims)
- **Mô hình LLM:** `None (retrieval-only)`
- **Tổng số ca kiểm thử:** **36** (26 câu có đáp án, 10 câu yêu cầu từ chối)

---

## 1. CHỈ SỐ TRUY XUẤT NGỮ NGHĨA (RETRIEVAL METRICS)

| Chỉ số đo lường | Giá trị | Định nghĩa toán học & Mẫu số | Đánh giá |
| :--- | :---: | :--- | :---: |
| **Hit Rate@1** | `84.6%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-1 (mẫu số: 26 ca) | Rất tốt |
| **Hit Rate@3** | `96.2%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-3 (mẫu số: 26 ca) | Xuất sắc |
| **Hit Rate@5** | `96.2%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-5 (mẫu số: 26 ca) | Xuất sắc |
| **Recall@1 (Doc-level)** | `80.8%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Tốt |
| **Recall@3 (Doc-level)** | `96.2%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Rất tốt |
| **Recall@5 (Doc-level)** | `96.2%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Xuất sắc |
| **Chunk-level Recall@5** | `96.2%` | Tỷ lệ chunk liên quan kỳ vọng được tìm thấy trong Top-5 | Xuất sắc |
| **Precision@5** | `20.8%` | \|Top-5 ∩ Expected\| / 5 (Đạt 96.4% trần lý thuyết 21.54%) | Mật độ tối ưu trong Top-5 |
| **Mean Reciprocal Rank (MRR@5)** | `0.8974` | 1/\|Q\| * Σ (1/Rank_1) = 23.3333 / 26 (Khớp tuyệt đối phân bố Rank) | Rất cao |
| **Retrieval Coverage** | `96.2%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | Toàn diện |
| **Empty Retrieval Rate** | `0.0%` | Tỷ lệ truy vấn trả về 0 chunk | Lý tưởng |
| **Empty Candidate Rate** | `0.0%` | Tỷ lệ truy vấn có 0 ứng viên từ tìm kiếm vector | Lý tưởng |
| **Empty Accepted Evidence Rate** | `0.0%` | Tỷ lệ truy vấn không có chunk nào đủ điều kiện vào context | Lý tưởng |
| **Tenant Isolation Rate** | `100.0%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace | **BẢO MẬT TUYỆT ĐỐI (100%)** |
| **Độ trễ trung bình truy xuất** | `566.25 ms` | Tổng thời gian nhúng câu hỏi + truy vấn vector | Bình thường |
| - *Độ trễ nhúng câu hỏi (Embedding)* | `328.00 ms` | Thời gian tính vector câu hỏi qua multilingual-e5-small | Dense Model |
| - *Độ trễ truy vấn vector (pgvector)* | `238.13 ms` | Thời gian quét pgvector HNSW cosine_distance trong CSDL | Live Database |
| - *Độ trễ lắp ráp ngữ cảnh (Context)* | `0.23 ms` | Thời gian lọc ký tự và tạo block [Source N] | Prompt Assembly |

---

## 2. PHÂN TÍCH THEO NHÓM KIỂM THỬ (CATEGORY BREAKDOWN)

| Phân loại kiểm thử | Số ca | Số ca đạt | Tỷ lệ đạt | Recall@5 trung bình |
| :--- | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_QUERY` | 3 | 2 | **66.7%** | 66.7% |
| `CROSS_WORKSPACE` | 3 | 3 | **100.0%** | 100.0% |
| `FACTUAL_EXACT` | 9 | 9 | **100.0%** | 100.0% |
| `INSUFFICIENT_INFO` | 4 | 4 | **100.0%** | N/A (Refusal) |
| `MULTI_DOC` | 4 | 4 | **100.0%** | 100.0% |
| `OUT_OF_DOMAIN` | 3 | 3 | **100.0%** | N/A (Refusal) |
| `PROMPT_INJECTION` | 3 | 3 | **100.0%** | 100.0% |
| `SEMANTIC_PARAPHRASE` | 7 | 7 | **100.0%** | 100.0% |

---

## 4. CHI TIẾT CÁC CA KIỂM THỬ KHÔNG ĐẠT (FAILED CASES DIAGNOSTICS)

### ❌ Case ID: `TC-AMB-QUERY-02` (AMBIGUOUS_QUERY)
- **Workspace:** `workspace_alpha` | **Difficulty:** `MEDIUM`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['doc_injection_safe', 'doc_pg_arch', 'doc_redis_governor', 'doc_celery_workers', 'doc_rag_pipeline']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

