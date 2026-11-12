# So sánh Dense vs Hybrid — `ai-knowledge-lab-rag-quality-holdout` v`1.0`

- Chiến lược: `dense (pgvector cosine)` vs `hybrid (pgvector + FTS + RRF k=60 w_d=1.0 w_k=0.4)`
- Embedding: `intfloat/multilingual-e5-small` | k=5 | DB: `ailab_eval_test`
- Số ca: 35 (30 có đáp án)

## 1. Chỉ số tổng hợp

| Chỉ số | Dense | Hybrid | Δ |
| :--- | :---: | :---: | :---: |
| `hit_rate_at_1` | 63.3% | 60.0% | -3.3pp |
| `hit_rate_at_3` | 76.7% | 80.0% | +3.3pp |
| `hit_rate_at_5` | 90.0% | 86.7% | -3.3pp |
| `recall_at_1` | 55.0% | 53.3% | -1.7pp |
| `recall_at_3` | 73.3% | 75.0% | +1.7pp |
| `recall_at_5` | 88.3% | 85.0% | -3.3pp |
| `precision_at_5` | 21.3% | 20.7% | -0.7pp |
| `mrr_at_5` | 0.7300 | 0.7022 | -0.0278 |
| `retrieval_coverage` | 90.0% | 86.7% | -3.3pp |
| `chunk_recall_at_5` | 87.5% | 83.3% | -4.2pp |
| `chunk_mrr_at_5` | 0.6937 | 0.6764 | -0.0173 |
| `tenant_isolation_rate` | 100.0% | 100.0% | +0.0pp |
| `empty_candidate_rate` | 0.0% | 0.0% | +0.0pp |
| `empty_accepted_evidence_rate` | 0.0% | 0.0% | +0.0pp |

## 2. Theo nhóm kiểm thử (category)

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_QUERY` | 3 (3/0) | 66.7% → 33.3% | 100.0% → 100.0% | 83.3% → 83.3% | 0.7500 → 0.6111 |
| `CROSS_LINGUAL` | 10 (10/0) | 10.0% → 10.0% | 80.0% → 70.0% | 80.0% → 70.0% | 0.3650 → 0.3233 |
| `CROSS_WORKSPACE` | 3 (1/2) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `EXACT_IDENTIFIER` | 6 (6/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `INSUFFICIENT_INFO` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `MULTI_CHUNK` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `MULTI_DOC` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `OUT_OF_DOMAIN` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `PROMPT_INJECTION` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `SEMANTIC_PARAPHRASE` | 4 (4/0) | 75.0% → 75.0% | 75.0% → 75.0% | 75.0% → 75.0% | 0.7500 → 0.7500 |

## 3. Theo ngôn ngữ truy vấn

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `en` | 19 (16/3) | 62.5% → 62.5% | 93.8% → 93.8% | 90.6% → 90.6% | 0.7469 → 0.7417 |
| `vi` | 16 (14/2) | 64.3% → 57.1% | 85.7% → 78.6% | 85.7% → 78.6% | 0.7107 → 0.6571 |

## 4. Theo thẻ kịch bản (tag)

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `ambiguous` | 3 (3/0) | 66.7% → 33.3% | 100.0% → 100.0% | 83.3% → 83.3% | 0.7500 → 0.6111 |
| `beta_authorized` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `chunk_index:0` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `cross_workspace` | 3 (1/2) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `evidence_in_overlap` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:config_param` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:enum_value` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:error_code` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:python_symbol` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `insufficient_info` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `lexical_overlap:exact` | 6 (6/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `lexical_overlap:none` | 7 (7/0) | 14.3% → 14.3% | 57.1% → 42.9% | 57.1% → 42.9% | 0.3143 → 0.2190 |
| `lexical_overlap:partial` | 7 (7/0) | 42.9% → 42.9% | 100.0% → 100.0% | 100.0% → 100.0% | 0.6357 → 0.6714 |
| `malicious` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `multi_chunk` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `multi_doc` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `multiple_plausible_documents` | 3 (3/0) | 66.7% → 33.3% | 100.0% → 100.0% | 83.3% → 83.3% | 0.7500 → 0.6111 |
| `out_of_domain` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `paraphrase` | 4 (4/0) | 75.0% → 75.0% | 75.0% → 75.0% | 75.0% → 75.0% | 0.7500 → 0.7500 |
| `prompt_injection` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `requires_two_sources` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `tenant_isolation` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `unanswerable` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `xling:en->vi` | 5 (5/0) | 0.0% → 20.0% | 80.0% → 80.0% | 80.0% → 80.0% | 0.3400 → 0.4067 |
| `xling:vi->en` | 5 (5/0) | 20.0% → 0.0% | 80.0% → 60.0% | 80.0% → 60.0% | 0.3900 → 0.2400 |

## 5. Thay đổi thứ hạng theo truy vấn

- **Cải thiện hạng tài liệu** (2): `H-XL-10`, `H-AMB-01`
- **Suy giảm hạng tài liệu** (6): `H-XL-01`, `H-XL-02`, `H-XL-05`, `H-XL-06`, `H-XL-09`, `H-AMB-03`
- Không đổi hạng tài liệu: 22
- **Chỉ Hybrid tìm thấy (Top-5)** (0): _không có_
- **Hybrid mất kết quả (Top-5)** (1): `H-XL-02`
- **Có đóng góp lexical vào tài liệu đúng** (23): `H-XL-01`, `H-XL-04`, `H-XL-05`, `H-XL-07`, `H-XL-10`, `H-ID-01`, `H-ID-02`, `H-ID-03`, `H-ID-04`, `H-ID-05`, `H-ID-06`, `H-PARA-01`, `H-PARA-02`, `H-PARA-03`, `H-AMB-01`, `H-AMB-02`, `H-MD-01`, `H-MD-02`, `H-MD-03`, `H-MC-01`, `H-MC-02`, `H-MC-03`, `H-SEC-03`
- **Cải thiện hạng chunk** (1): `H-XL-10`
- **Suy giảm hạng chunk** (5): `H-XL-01`, `H-XL-02`, `H-XL-05`, `H-XL-06`, `H-XL-09`
- Ca có thứ tự Top-5 khác nhau: 23/35

| Case | Nhóm | Hạng doc D→H | Trạng thái | Hạng chunk D→H | Lexical |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `H-XL-01` | CROSS_LINGUAL | 1 → 2 | regressed | 1 → 2 (regressed) | có |
| `H-XL-02` | CROSS_LINGUAL | 5 → None | regressed | 5 → None (regressed) | không |
| `H-XL-03` | CROSS_LINGUAL | None → None | unchanged | None → None (unchanged) | không |
| `H-XL-04` | CROSS_LINGUAL | 2 → 2 | unchanged | 2 → 2 (unchanged) | có |
| `H-XL-05` | CROSS_LINGUAL | 4 → 5 | regressed | 4 → 5 (regressed) | có |
| `H-XL-06` | CROSS_LINGUAL | 2 → 5 | regressed | 2 → 5 (regressed) | không |
| `H-XL-07` | CROSS_LINGUAL | 2 → 2 | unchanged | 2 → 2 (unchanged) | có |
| `H-XL-08` | CROSS_LINGUAL | None → None | unchanged | None → None (unchanged) | không |
| `H-XL-09` | CROSS_LINGUAL | 2 → 3 | regressed | 2 → 3 (regressed) | không |
| `H-XL-10` | CROSS_LINGUAL | 5 → 1 | improved | 5 → 1 (improved) | có |
| `H-ID-01` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-ID-02` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-ID-03` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-ID-04` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-ID-05` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-ID-06` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-PARA-01` | SEMANTIC_PARAPHRASE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-PARA-02` | SEMANTIC_PARAPHRASE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-PARA-03` | SEMANTIC_PARAPHRASE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-PARA-04` | SEMANTIC_PARAPHRASE | None → None | unchanged | None → None (unchanged) | không |
| `H-AMB-01` | AMBIGUOUS_QUERY | 4 → 3 | improved | — | có |
| `H-AMB-02` | AMBIGUOUS_QUERY | 1 → 1 | unchanged | — | có |
| `H-AMB-03` | AMBIGUOUS_QUERY | 1 → 2 | regressed | — | không |
| `H-MD-01` | MULTI_DOC | 1 → 1 | unchanged | — | có |
| `H-MD-02` | MULTI_DOC | 1 → 1 | unchanged | — | có |
| `H-MD-03` | MULTI_DOC | 1 → 1 | unchanged | — | có |
| `H-MC-01` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-MC-02` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-MC-03` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `H-SEC-03` | CROSS_WORKSPACE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
