# So sánh Dense vs Hybrid — `ai-knowledge-lab-rag-quality-extended` v`1.0`

- Chiến lược: `dense (pgvector cosine)` vs `hybrid (pgvector + FTS + RRF k=60 w_d=1.0 w_k=0.4)`
- Embedding: `intfloat/multilingual-e5-small` | k=5 | DB: `ailab_eval_test`
- Số ca: 41 (32 có đáp án)

## 1. Chỉ số tổng hợp

| Chỉ số | Dense | Hybrid | Δ |
| :--- | :---: | :---: | :---: |
| `hit_rate_at_1` | 78.1% | 81.2% | +3.1pp |
| `hit_rate_at_3` | 81.2% | 87.5% | +6.2pp |
| `hit_rate_at_5` | 90.6% | 87.5% | -3.1pp |
| `recall_at_1` | 70.3% | 71.9% | +1.6pp |
| `recall_at_3` | 76.6% | 82.8% | +6.2pp |
| `recall_at_5` | 85.9% | 82.8% | -3.1pp |
| `precision_at_5` | 20.0% | 19.4% | -0.6pp |
| `mrr_at_5` | 0.8187 | 0.8385 | +0.0198 |
| `retrieval_coverage` | 90.6% | 87.5% | -3.1pp |
| `chunk_recall_at_5` | 85.9% | 82.8% | -3.1pp |
| `chunk_mrr_at_5` | 0.8031 | 0.8385 | +0.0354 |
| `tenant_isolation_rate` | 100.0% | 100.0% | +0.0pp |
| `empty_candidate_rate` | 0.0% | 0.0% | +0.0pp |
| `empty_accepted_evidence_rate` | 0.0% | 0.0% | +0.0pp |

## 2. Theo nhóm kiểm thử (category)

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `AMBIGUOUS_QUERY` | 5 (5/0) | 60.0% → 80.0% | 80.0% → 80.0% | 70.0% → 70.0% | 0.7000 → 0.8000 |
| `CROSS_LINGUAL` | 9 (9/0) | 44.4% → 44.4% | 77.8% → 66.7% | 77.8% → 66.7% | 0.5222 → 0.5370 |
| `CROSS_WORKSPACE` | 5 (2/3) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `EXACT_IDENTIFIER` | 9 (9/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `INSUFFICIENT_INFO` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `MALICIOUS_QUERY` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `MULTI_CHUNK` | 4 (4/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `MULTI_DOC` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 50.0% → 50.0% | 1.0000 → 1.0000 |
| `OUT_OF_DOMAIN` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `PROMPT_INJECTION` | 2 (1/1) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |

## 3. Theo ngôn ngữ truy vấn

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `en` | 32 (24/8) | 83.3% → 87.5% | 95.8% → 91.7% | 91.7% → 87.5% | 0.8729 → 0.8889 |
| `vi` | 9 (8/1) | 62.5% → 62.5% | 75.0% → 75.0% | 68.8% → 68.8% | 0.6562 → 0.6875 |

## 4. Theo thẻ kịch bản (tag)

| Nhóm | Ca (đáp án/từ chối) | Hit@1 D→H | Hit@5 D→H | Recall@5 D→H | MRR@5 D→H |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `beta_positive` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `bilingual_term` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `control` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `distractor_chunks` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `evidence_in_multiple_chunks` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:abbreviation` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:api_endpoint` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:db_column` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:error_code` | 3 (3/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:python_symbol` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier:sql_expression` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `identifier_collision` | 2 (1/1) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `lexical_overlap:abbreviation_only` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `lexical_overlap:exact` | 8 (8/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `lexical_overlap:high` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `lexical_overlap:none` | 4 (4/0) | 0.0% → 0.0% | 50.0% → 25.0% | 50.0% → 25.0% | 0.1125 → 0.0833 |
| `lexical_overlap:term_only` | 4 (4/0) | 75.0% → 75.0% | 100.0% → 100.0% | 100.0% → 100.0% | 0.8125 → 0.8750 |
| `monolingual:vi` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `multi_chunk_doc` | 8 (8/0) | 62.5% → 75.0% | 100.0% → 100.0% | 87.5% → 87.5% | 0.7500 → 0.8542 |
| `multi_doc` | 2 (2/0) | 100.0% → 100.0% | 100.0% → 100.0% | 50.0% → 50.0% | 1.0000 → 1.0000 |
| `multiple_plausible_documents` | 4 (4/0) | 75.0% → 75.0% | 75.0% → 75.0% | 75.0% → 75.0% | 0.7500 → 0.7500 |
| `out_of_domain` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `prompt_injection_in_document` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `prompt_injection_in_query` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `requires_two_sources` | 2 (2/0) | 50.0% → 100.0% | 100.0% → 100.0% | 50.0% → 50.0% | 0.7500 → 1.0000 |
| `short_query` | 4 (4/0) | 75.0% → 75.0% | 75.0% → 75.0% | 75.0% → 75.0% | 0.7500 → 0.7500 |
| `sql_injection_pattern` | 2 (0/2) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `sql_syntax_in_query` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `tenant_decoy` | 1 (1/0) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `tenant_isolation` | 6 (2/4) | 100.0% → 100.0% | 100.0% → 100.0% | 100.0% → 100.0% | 1.0000 → 1.0000 |
| `unanswerable_in_domain` | 1 (0/1) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `unauthorized_document` | 3 (0/3) | N/A → N/A | N/A → N/A | N/A → N/A | N/A → N/A |
| `underspecified` | 4 (4/0) | 75.0% → 75.0% | 75.0% → 75.0% | 75.0% → 75.0% | 0.7500 → 0.7500 |
| `xling:en->vi` | 8 (8/0) | 50.0% → 62.5% | 87.5% → 75.0% | 75.0% → 62.5% | 0.6188 → 0.6667 |
| `xling:vi->en` | 6 (6/0) | 50.0% → 50.0% | 66.7% → 66.7% | 58.3% → 58.3% | 0.5417 → 0.5833 |

## 5. Thay đổi thứ hạng theo truy vấn

- **Cải thiện hạng tài liệu** (3): `X-XL-07`, `X-XL-09`, `X-AMB-05`
- **Suy giảm hạng tài liệu** (1): `X-XL-06`
- Không đổi hạng tài liệu: 28
- **Chỉ Hybrid tìm thấy (Top-5)** (0): _không có_
- **Hybrid mất kết quả (Top-5)** (1): `X-XL-06`
- **Có đóng góp lexical vào tài liệu đúng** (28): `X-ID-01`, `X-ID-02`, `X-ID-03`, `X-ID-04`, `X-ID-05`, `X-ID-06`, `X-ID-07`, `X-ID-08`, `X-ID-09`, `X-XL-03`, `X-XL-04`, `X-XL-05`, `X-XL-07`, `X-XL-08`, `X-XL-09`, `X-MC-01`, `X-MC-02`, `X-MC-03`, `X-MC-04`, `X-MD-01`, `X-MD-02`, `X-AMB-01`, `X-AMB-02`, `X-AMB-03`, `X-AMB-05`, `X-SEC-04`, `X-SEC-05`, `X-SEC-06`
- **Cải thiện hạng chunk** (4): `X-XL-07`, `X-XL-09`, `X-MC-01`, `X-AMB-05`
- **Suy giảm hạng chunk** (1): `X-XL-06`
- Ca có thứ tự Top-5 khác nhau: 23/41

| Case | Nhóm | Hạng doc D→H | Trạng thái | Hạng chunk D→H | Lexical |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `X-ID-01` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-02` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-03` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-04` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-05` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-06` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-07` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-08` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-ID-09` | EXACT_IDENTIFIER | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-XL-01` | CROSS_LINGUAL | None → None | unchanged | None → None (unchanged) | không |
| `X-XL-02` | CROSS_LINGUAL | None → None | unchanged | None → None (unchanged) | không |
| `X-XL-03` | CROSS_LINGUAL | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-XL-04` | CROSS_LINGUAL | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-XL-05` | CROSS_LINGUAL | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-XL-06` | CROSS_LINGUAL | 5 → None | regressed | 5 → None (regressed) | không |
| `X-XL-07` | CROSS_LINGUAL | 4 → 3 | improved | 4 → 3 (improved) | có |
| `X-XL-08` | CROSS_LINGUAL | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-XL-09` | CROSS_LINGUAL | 4 → 2 | improved | 4 → 2 (improved) | có |
| `X-MC-01` | MULTI_CHUNK | 1 → 1 | unchanged | 2 → 1 (improved) | có |
| `X-MC-02` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-MC-03` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-MC-04` | MULTI_CHUNK | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-MD-01` | MULTI_DOC | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-MD-02` | MULTI_DOC | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-AMB-01` | AMBIGUOUS_QUERY | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-AMB-02` | AMBIGUOUS_QUERY | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-AMB-03` | AMBIGUOUS_QUERY | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-AMB-04` | AMBIGUOUS_QUERY | None → None | unchanged | None → None (unchanged) | không |
| `X-AMB-05` | AMBIGUOUS_QUERY | 2 → 1 | improved | 2 → 1 (improved) | có |
| `X-SEC-04` | CROSS_WORKSPACE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-SEC-05` | CROSS_WORKSPACE | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
| `X-SEC-06` | PROMPT_INJECTION | 1 → 1 | unchanged | 1 → 1 (unchanged) | có |
