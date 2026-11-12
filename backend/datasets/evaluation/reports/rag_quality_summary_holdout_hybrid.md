# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG & TRUY VẤN NGỮ NGHĨA (AI-KNOWLEDGE-LAB-RAG-QUALITY-HOLDOUT)

- **Phiên bản Dataset:** `1.0`
- **Thời điểm đánh giá:** `2026-11-12T04:05:09.269499+00:00`
- **Chế độ thực thi:** `retrieval-only`
- **Chiến lược truy xuất:** `hybrid (pgvector + FTS + RRF k=60 w_d=1.0 w_k=0.4)`
- **Môi trường CSDL:** `ailab_eval_test`
- **Mô hình nhúng (Embedding):** `intfloat/multilingual-e5-small` (384 dims)
- **Mô hình LLM:** `None (retrieval-only)`
- **Tổng số ca kiểm thử:** **35** (30 câu có đáp án, 5 câu yêu cầu từ chối)

---

## 1. CHỈ SỐ TRUY XUẤT NGỮ NGHĨA (RETRIEVAL METRICS)

| Chỉ số đo lường | Giá trị | Định nghĩa toán học & Mẫu số | Đánh giá |
| :--- | :---: | :--- | :---: |
| **Hit Rate@1** | `60.0%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-1 (mẫu số: 30 ca) | Khá |
| **Hit Rate@3** | `80.0%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-3 (mẫu số: 30 ca) | Khá |
| **Hit Rate@5** | `86.7%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-5 (mẫu số: 30 ca) | Khá |
| **Recall@1 (Doc-level)** | `53.3%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Cần tối ưu |
| **Recall@3 (Doc-level)** | `75.0%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Trung bình |
| **Recall@5 (Doc-level)** | `85.0%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Đạt yêu cầu |
| **Chunk-level Recall@5** | `83.3%` | Tỷ lệ chunk liên quan kỳ vọng được tìm thấy trong Top-5 | Đạt |
| **Precision@5** | `20.7%` | \|Top-5 ∩ Expected\| / 5 (trần lý thuyết = số tài liệu kỳ vọng / 5) | Mật độ trong Top-5 |
| **Mean Reciprocal Rank (MRR@5)** | `0.7022` | 1/\|Q\| * Σ (1/Rank_1) = 21.0660 / 30 | Khá |
| **Retrieval Coverage** | `86.7%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | Cần chú ý |
| **Empty Retrieval Rate** | `0.0%` | Tỷ lệ truy vấn trả về 0 chunk | Lý tưởng |
| **Empty Candidate Rate** | `0.0%` | Tỷ lệ truy vấn có 0 ứng viên từ tìm kiếm vector | Lý tưởng |
| **Empty Accepted Evidence Rate** | `0.0%` | Tỷ lệ truy vấn không có chunk nào đủ điều kiện vào context | Lý tưởng |
| **Tenant Isolation Rate** | `100.0%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace | **BẢO MẬT TUYỆT ĐỐI (100%)** |
| **Độ trễ trung bình truy xuất** | `295.09 ms` | Tổng thời gian nhúng câu hỏi + truy vấn vector | Bình thường |
| - *Độ trễ nhúng câu hỏi (Embedding)* | `98.20 ms` | Thời gian tính vector câu hỏi qua multilingual-e5-small | Dense Model |
| - *Độ trễ truy vấn vector (pgvector)* | `165.74 ms` | Thời gian quét pgvector HNSW cosine_distance trong CSDL | Live Database |
| - *Độ trễ lắp ráp ngữ cảnh (Context)* | `0.12 ms` | Thời gian lọc ký tự và tạo block [Source N] | Prompt Assembly |

---

## 2. PHÂN TÍCH THEO NHÓM KIỂM THỬ (CATEGORY BREAKDOWN)

| Phân loại kiểm thử | Số ca | Số ca đạt | Tỷ lệ đạt | Recall@5 trung bình |
| :--- | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_QUERY` | 3 | 3 | **100.0%** | 83.3% |
| `CROSS_LINGUAL` | 10 | 7 | **70.0%** | 70.0% |
| `CROSS_WORKSPACE` | 3 | 3 | **100.0%** | 100.0% |
| `EXACT_IDENTIFIER` | 6 | 6 | **100.0%** | 100.0% |
| `INSUFFICIENT_INFO` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `MULTI_CHUNK` | 3 | 3 | **100.0%** | 100.0% |
| `MULTI_DOC` | 3 | 3 | **100.0%** | 100.0% |
| `OUT_OF_DOMAIN` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `PROMPT_INJECTION` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `SEMANTIC_PARAPHRASE` | 4 | 3 | **75.0%** | 75.0% |

### PHÂN TÍCH THEO NGÔN NGỮ TRUY VẤN (LANGUAGE BREAKDOWN)

| Nhóm | Số ca | Có đáp án | Hit@1 | Hit@5 | Recall@5 | MRR@5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `en` | 19 | 16 | 62.5% | 93.8% | 90.6% | 0.7417 |
| `vi` | 16 | 14 | 57.1% | 78.6% | 78.6% | 0.6571 |

### PHÂN TÍCH THEO THẺ KỊCH BẢN (TAG BREAKDOWN)

| Nhóm | Số ca | Có đáp án | Hit@1 | Hit@5 | Recall@5 | MRR@5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `ambiguous` | 3 | 3 | 33.3% | 100.0% | 83.3% | 0.6111 |
| `beta_authorized` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `chunk_index:0` | 2 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `cross_workspace` | 3 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `evidence_in_overlap` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:config_param` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:enum_value` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:error_code` | 3 | 3 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:python_symbol` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `insufficient_info` | 1 | 0 | N/A | N/A | N/A | N/A |
| `lexical_overlap:exact` | 6 | 6 | 100.0% | 100.0% | 100.0% | 1.0 |
| `lexical_overlap:none` | 7 | 7 | 14.3% | 42.9% | 42.9% | 0.219 |
| `lexical_overlap:partial` | 7 | 7 | 42.9% | 100.0% | 100.0% | 0.6714 |
| `malicious` | 1 | 0 | N/A | N/A | N/A | N/A |
| `multi_chunk` | 3 | 3 | 100.0% | 100.0% | 100.0% | 1.0 |
| `multi_doc` | 3 | 3 | 100.0% | 100.0% | 100.0% | 1.0 |
| `multiple_plausible_documents` | 3 | 3 | 33.3% | 100.0% | 83.3% | 0.6111 |
| `out_of_domain` | 1 | 0 | N/A | N/A | N/A | N/A |
| `paraphrase` | 4 | 4 | 75.0% | 75.0% | 75.0% | 0.75 |
| `prompt_injection` | 1 | 0 | N/A | N/A | N/A | N/A |
| `requires_two_sources` | 3 | 3 | 100.0% | 100.0% | 100.0% | 1.0 |
| `tenant_isolation` | 2 | 0 | N/A | N/A | N/A | N/A |
| `unanswerable` | 2 | 0 | N/A | N/A | N/A | N/A |
| `xling:en->vi` | 5 | 5 | 20.0% | 80.0% | 80.0% | 0.4067 |
| `xling:vi->en` | 5 | 5 | 0.0% | 60.0% | 60.0% | 0.24 |

---

## 4. CHI TIẾT CÁC CA KIỂM THỬ KHÔNG ĐẠT (FAILED CASES DIAGNOSTICS)

### ❌ Case ID: `H-XL-02` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['holdout_vi_vector_indexing', 'holdout_vi_incident_runbook', 'holdout_vi_circuit_breaker', 'holdout_vi_cdc_pipeline', 'holdout_vi_k8s_autoscaling']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `H-XL-03` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['holdout_vi_incident_runbook', 'holdout_vi_rate_limiting', 'holdout_vi_circuit_breaker', 'holdout_vi_cdc_pipeline', 'holdout_vi_vector_indexing']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `H-XL-08` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['holdout_en_cdc_pipeline', 'holdout_en_circuit_breaker', 'holdout_en_rate_limiting', 'holdout_en_vector_indexing', 'holdout_en_k8s_autoscaling']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `H-PARA-04` (SEMANTIC_PARAPHRASE)
- **Workspace:** `workspace_alpha` | **Difficulty:** `MEDIUM`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['holdout_vi_k8s_autoscaling', 'holdout_vi_incident_runbook', 'holdout_vi_rate_limiting', 'holdout_vi_circuit_breaker', 'holdout_vi_vector_indexing']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

