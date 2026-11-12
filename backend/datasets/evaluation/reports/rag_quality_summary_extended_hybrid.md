# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG RAG & TRUY VẤN NGỮ NGHĨA (AI-KNOWLEDGE-LAB-RAG-QUALITY-EXTENDED)

- **Phiên bản Dataset:** `1.0`
- **Thời điểm đánh giá:** `2026-11-12T02:40:14.126346+00:00`
- **Chế độ thực thi:** `retrieval-only`
- **Chiến lược truy xuất:** `hybrid (pgvector + FTS + RRF k=60 w_d=1.0 w_k=0.4)`
- **Môi trường CSDL:** `ailab_eval_test`
- **Mô hình nhúng (Embedding):** `intfloat/multilingual-e5-small` (384 dims)
- **Mô hình LLM:** `None (retrieval-only)`
- **Tổng số ca kiểm thử:** **41** (32 câu có đáp án, 9 câu yêu cầu từ chối)

---

## 1. CHỈ SỐ TRUY XUẤT NGỮ NGHĨA (RETRIEVAL METRICS)

| Chỉ số đo lường | Giá trị | Định nghĩa toán học & Mẫu số | Đánh giá |
| :--- | :---: | :--- | :---: |
| **Hit Rate@1** | `81.2%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-1 (mẫu số: 32 ca) | Rất tốt |
| **Hit Rate@3** | `87.5%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-3 (mẫu số: 32 ca) | Khá |
| **Hit Rate@5** | `87.5%` | Tỷ lệ câu hỏi có ít nhất 1 tài liệu đúng trong Top-5 (mẫu số: 32 ca) | Khá |
| **Recall@1 (Doc-level)** | `71.9%` | Macro-average: \|Top-1 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Tốt |
| **Recall@3 (Doc-level)** | `82.8%` | Macro-average: \|Top-3 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Trung bình |
| **Recall@5 (Doc-level)** | `82.8%` | Macro-average: \|Top-5 ∩ Expected\| / \|Expected\| (chia đều theo câu hỏi) | Đạt yêu cầu |
| **Chunk-level Recall@5** | `82.8%` | Tỷ lệ chunk liên quan kỳ vọng được tìm thấy trong Top-5 | Đạt |
| **Precision@5** | `19.4%` | \|Top-5 ∩ Expected\| / 5 (trần lý thuyết = số tài liệu kỳ vọng / 5) | Mật độ trong Top-5 |
| **Mean Reciprocal Rank (MRR@5)** | `0.8385` | 1/\|Q\| * Σ (1/Rank_1) = 26.8320 / 32 | Rất cao |
| **Retrieval Coverage** | `87.5%` | Tỷ lệ câu hỏi tìm thấy ít nhất 1 tài liệu đúng trong Top-5 (Coverage@5) | Cần chú ý |
| **Empty Retrieval Rate** | `0.0%` | Tỷ lệ truy vấn trả về 0 chunk | Lý tưởng |
| **Empty Candidate Rate** | `0.0%` | Tỷ lệ truy vấn có 0 ứng viên từ tìm kiếm vector | Lý tưởng |
| **Empty Accepted Evidence Rate** | `0.0%` | Tỷ lệ truy vấn không có chunk nào đủ điều kiện vào context | Lý tưởng |
| **Tenant Isolation Rate** | `100.0%` | Tỷ lệ truy vấn hoàn toàn không rò rỉ dữ liệu chéo workspace | **BẢO MẬT TUYỆT ĐỐI (100%)** |
| **Độ trễ trung bình truy xuất** | `236.70 ms` | Tổng thời gian nhúng câu hỏi + truy vấn vector | Bình thường |
| - *Độ trễ nhúng câu hỏi (Embedding)* | `73.33 ms` | Thời gian tính vector câu hỏi qua multilingual-e5-small | Dense Model |
| - *Độ trễ truy vấn vector (pgvector)* | `134.20 ms` | Thời gian quét pgvector HNSW cosine_distance trong CSDL | Live Database |
| - *Độ trễ lắp ráp ngữ cảnh (Context)* | `0.11 ms` | Thời gian lọc ký tự và tạo block [Source N] | Prompt Assembly |

---

## 2. PHÂN TÍCH THEO NHÓM KIỂM THỬ (CATEGORY BREAKDOWN)

| Phân loại kiểm thử | Số ca | Số ca đạt | Tỷ lệ đạt | Recall@5 trung bình |
| :--- | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_QUERY` | 5 | 4 | **80.0%** | 70.0% |
| `CROSS_LINGUAL` | 9 | 6 | **66.7%** | 66.7% |
| `CROSS_WORKSPACE` | 5 | 5 | **100.0%** | 100.0% |
| `EXACT_IDENTIFIER` | 9 | 9 | **100.0%** | 100.0% |
| `INSUFFICIENT_INFO` | 1 | 1 | **100.0%** | N/A (Refusal) |
| `MALICIOUS_QUERY` | 2 | 2 | **100.0%** | N/A (Refusal) |
| `MULTI_CHUNK` | 4 | 4 | **100.0%** | 100.0% |
| `MULTI_DOC` | 2 | 2 | **100.0%** | 50.0% |
| `OUT_OF_DOMAIN` | 2 | 2 | **100.0%** | N/A (Refusal) |
| `PROMPT_INJECTION` | 2 | 2 | **100.0%** | 100.0% |

### PHÂN TÍCH THEO NGÔN NGỮ TRUY VẤN (LANGUAGE BREAKDOWN)

| Nhóm | Số ca | Có đáp án | Hit@1 | Hit@5 | Recall@5 | MRR@5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `en` | 32 | 24 | 87.5% | 91.7% | 87.5% | 0.8889 |
| `vi` | 9 | 8 | 62.5% | 75.0% | 68.8% | 0.6875 |

### PHÂN TÍCH THEO THẺ KỊCH BẢN (TAG BREAKDOWN)

| Nhóm | Số ca | Có đáp án | Hit@1 | Hit@5 | Recall@5 | MRR@5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `beta_positive` | 2 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `bilingual_term` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `control` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `distractor_chunks` | 2 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `evidence_in_multiple_chunks` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:abbreviation` | 2 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:api_endpoint` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:db_column` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:error_code` | 3 | 3 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:python_symbol` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier:sql_expression` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `identifier_collision` | 2 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `lexical_overlap:abbreviation_only` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `lexical_overlap:exact` | 8 | 8 | 100.0% | 100.0% | 100.0% | 1.0 |
| `lexical_overlap:high` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `lexical_overlap:none` | 4 | 4 | 0.0% | 25.0% | 25.0% | 0.0833 |
| `lexical_overlap:term_only` | 4 | 4 | 75.0% | 100.0% | 100.0% | 0.875 |
| `monolingual:vi` | 2 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `multi_chunk_doc` | 8 | 8 | 75.0% | 100.0% | 87.5% | 0.8542 |
| `multi_doc` | 2 | 2 | 100.0% | 100.0% | 50.0% | 1.0 |
| `multiple_plausible_documents` | 4 | 4 | 75.0% | 75.0% | 75.0% | 0.75 |
| `out_of_domain` | 2 | 0 | N/A | N/A | N/A | N/A |
| `prompt_injection_in_document` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `prompt_injection_in_query` | 1 | 0 | N/A | N/A | N/A | N/A |
| `requires_two_sources` | 2 | 2 | 100.0% | 100.0% | 50.0% | 1.0 |
| `short_query` | 4 | 4 | 75.0% | 75.0% | 75.0% | 0.75 |
| `sql_injection_pattern` | 2 | 0 | N/A | N/A | N/A | N/A |
| `sql_syntax_in_query` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `tenant_decoy` | 1 | 1 | 100.0% | 100.0% | 100.0% | 1.0 |
| `tenant_isolation` | 6 | 2 | 100.0% | 100.0% | 100.0% | 1.0 |
| `unanswerable_in_domain` | 1 | 0 | N/A | N/A | N/A | N/A |
| `unauthorized_document` | 3 | 0 | N/A | N/A | N/A | N/A |
| `underspecified` | 4 | 4 | 75.0% | 75.0% | 75.0% | 0.75 |
| `xling:en->vi` | 8 | 8 | 62.5% | 75.0% | 62.5% | 0.6667 |
| `xling:vi->en` | 6 | 6 | 50.0% | 66.7% | 58.3% | 0.5833 |

---

## 4. CHI TIẾT CÁC CA KIỂM THỬ KHÔNG ĐẠT (FAILED CASES DIAGNOSTICS)

### ❌ Case ID: `X-XL-01` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['ext_vi_backup', 'ext_vi_long_guide', 'ext_vi_long_guide', 'ext_vi_long_guide', 'ext_vi_sec_roles']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `X-XL-02` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['ext_vi_long_guide', 'ext_vi_incident', 'ext_vi_long_guide', 'ext_vi_backup', 'ext_vi_long_guide']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `X-XL-06` (CROSS_LINGUAL)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['ext_api_endpoints', 'ext_en_onboarding', 'ext_error_codes', 'ext_en_log_retention', 'ext_python_symbols']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

### ❌ Case ID: `X-AMB-04` (AMBIGUOUS_QUERY)
- **Workspace:** `workspace_alpha` | **Difficulty:** `HARD`
- **Recall@5:** `0.0` | **Precision@5:** `0.0`
- **Retrieved Document Keys:** `['ext_en_worker_maintenance', 'ext_rate_limit_policy', 'ext_error_codes', 'ext_celery_concurrency', 'ext_en_onboarding']`
- **Classification:** `INSUFFICIENT_EVIDENCE_TO_GRADE`
- **Root Cause:** `WRONG_DOCUMENT_RANKING`
- **Ghi chú lỗi:** Retrieval failed to find expected evidence in top-k

