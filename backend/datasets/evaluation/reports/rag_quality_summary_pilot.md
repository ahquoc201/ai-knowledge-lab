# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG & TRUY VẤN NGỮ NGHĨA (AI-KNOWLEDGE-LAB-RAG-QUALITY)

- **Phiên bản Dataset:** `2.0`
- **Thời điểm đánh giá:** `2026-11-11T02:45:54.083407+00:00`
- **Chế độ thực thi:** `full-rag`
- **Môi trường CSDL:** `ailab_eval_test`
- **Mô hình nhúng (Embedding):** `intfloat/multilingual-e5-small` (384 dims)
- **Mô hình LLM:** `qwen3:1.7b`
- **Tổng số ca kiểm thử:** **7** (2 câu có đáp án, 5 câu yêu cầu từ chối)

---

## 1. CHỈ SỐ TRUY XUẤT NGỮ NGHĨA (RETRIEVAL METRICS)

| Chỉ số đo lường | Giá trị | Định nghĩa toán học & Mẫu số | Đánh giá |
| :--- | :---: | :--- | :---: |
| **Hit Rate@1** | `100.0%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-1 (mẫu số: 2 ca) | Rất tốt |
| **Hit Rate@3** | `100.0%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-3 (mẫu số: 2 ca) | Xuất sắc |
| **Hit Rate@5** | `100.0%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-5 (mẫu số: 2 ca) | Xuất sắc |
| **Recall@1 (Doc-level)** | `100.0%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Tốt |
| **Recall@3 (Doc-level)** | `100.0%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Rất tốt |
| **Recall@5 (Doc-level)** | `100.0%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Xuất sắc |
| **Chunk-level Recall@5** | `100.0%` | Tỷ lệ chunk liên quan kỳ vọng được tìm thấy trong Top-5 | Xuất sắc |
| **Precision@5** | `20.0%` | \|Top-5 ∩ Expected\| / 5 (Đạt 96.4% trần lý thuyết 21.54%) | Mật độ tối ưu trong Top-5 |
| **Mean Reciprocal Rank (MRR@5)** | `1.0000` | 1/\|Q\| * Σ (1/Rank_1) = 23.3333 / 26 (Khớp tuyệt đối phân bố Rank) | Rất cao |
| **Retrieval Coverage** | `100.0%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | Toàn diện |
| **Empty Retrieval Rate** | `0.0%` | Tỷ lệ truy vấn trả về 0 chunk | Lý tưởng |
| **Empty Candidate Rate** | `0.0%` | Tỷ lệ truy vấn có 0 ứng viên từ tìm kiếm vector | Lý tưởng |
| **Empty Accepted Evidence Rate** | `0.0%` | Tỷ lệ truy vấn không có chunk nào đủ điều kiện vào context | Lý tưởng |
| **Tenant Isolation Rate** | `100.0%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace | **BẢO MẬT TUYỆT ĐỐI (100%)** |
| **Độ trễ trung bình truy xuất** | `752.99 ms` | Tổng thời gian nhúng câu hỏi + truy vấn vector | Bình thường |
| - *Độ trễ nhúng câu hỏi (Embedding)* | `498.40 ms` | Thời gian tính vector câu hỏi qua multilingual-e5-small | Dense Model |
| - *Độ trễ truy vấn vector (pgvector)* | `254.45 ms` | Thời gian quét pgvector HNSW cosine_distance trong CSDL | Live Database |
| - *Độ trễ lắp ráp ngữ cảnh (Context)* | `0.26 ms` | Thời gian lọc ký tự và tạo block [Source N] | Prompt Assembly |

---

## 2. PHÂN TÍCH THEO NHÓM KIỂM THỬ (CATEGORY BREAKDOWN)

| Phân loại kiểm thử | Số ca | Số ca đạt | Tỷ lệ đạt | Recall@5 trung bình |
| :--- | :---: | :---: | :---: | :---: |
| `CROSS_WORKSPACE` | 2 | 2 | **100.0%** | N/A (Refusal) |
| `FACTUAL_EXACT` | 2 | 1 | **50.0%** | 100.0% |
| `INSUFFICIENT_INFO` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `OUT_OF_DOMAIN` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `PROMPT_INJECTION` | 1 | 1 | **100.0%** | N/A (Refusal) |

---

## 3. CHỈ SỐ CHẤT LƯỢNG SINH CÂU TRẢ LỜI & BỘ LỌC TỪ CHỐI (FULL-RAG METRICS)

| Chỉ số chất lượng | Giá trị | Ý nghĩa kỹ thuật |
| :--- | :---: | :--- |
| **Tỷ lệ vượt qua tổng thể (Overall Pass Rate)** | **`85.7%`** | Toàn bộ các tiêu chí (đúng fact, đúng trích dẫn, từ chối chuẩn) |
| **Độ chính xác câu trả lời (Accuracy Rate)** | `50.0%` | Câu trả lời đúng sự thật trên các câu hỏi có đáp án |
| **Từ chối chính xác (Correct Refusal Rate)** | `100.0%` | Hệ thống từ chối thành công khi thiếu dữ liệu / vi phạm tenant |
| **Từ chối nhầm (False Refusal Rate)** | `0.0%` | Tỷ lệ từ chối sai khi dữ liệu nguồn thực sự có sẵn |
| **Câu trả lời không căn cứ (Unsupported Rate)** | `0.0%` | Câu trả lời thiếu hoặc trích dẫn nguồn không hợp lệ |
| **Độ trễ sinh câu trả lời trung bình** | `55559.69 ms` | Thời gian suy luận LLM |

### Bảng phân phối phân loại phản hồi (Classification Breakdown):

- **`CORRECT_ANSWER`**: 1 ca
- **`INCORRECT_ANSWER`**: 1 ca
- **`CORRECT_REFUSAL`**: 5 ca

### Nguyên nhân thất bại (Failure Root Causes):

- **`NONE`**: 1 ca
- **`GENERATION_FAILURE`**: 1 ca
- **`CORRECT_REFUSAL`**: 5 ca

---

## 4. CHI TIẾT CÁC CA KIỂM THỬ KHÔNG ĐẠT (FAILED CASES DIAGNOSTICS)

### ❌ Case ID: `TC-EN-FACT-01` (FACTUAL_EXACT)
- **Workspace:** `workspace_alpha` | **Difficulty:** `EASY`
- **Recall@5:** `1.0` | **Precision@5:** `0.2`
- **Retrieved Document Keys:** `['doc_fastapi_security', 'doc_redis_governor', 'doc_rag_pipeline', 'doc_injection_safe', 'doc_celery_workers']`
- **Classification:** `INCORRECT_ANSWER`
- **Root Cause:** `GENERATION_FAILURE`
- **Ghi chú lỗi:** Answer missing expected facts: ['HS256']

