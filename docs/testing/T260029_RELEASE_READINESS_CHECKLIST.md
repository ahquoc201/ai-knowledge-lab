# T260029 — BẢNG KIỂM TRA TÍNH SẴN SÀNG PHÁT HÀNH (RELEASE READINESS CHECKLIST)
**Dự án:** AI Knowledge Lab
**Mã tài liệu:** `T260029-CHECKLIST`
**Nhánh áp dụng:** `feature/T260029`
**Commit HEAD:** `2011408e4cf8cfbe346a94fa6421fda361eb24eb`
**Ngày cập nhật:** 2026-11-09

---

## BẢNG ĐÁNH GIÁ CHI TIẾT 20 CỔNG KIỂM SOÁT PHÁT HÀNH (20 RELEASE GATES)

| Cổng kiểm soát (Gate) | Tiêu chí kỳ vọng (Expected) | Kết quả thực tế quan sát (Actual) | Trạng thái (Status) | Phân loại Blocker (Dev / Staging / Prod) | Bằng chứng thực tế (Evidence) |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **1. Git Integrity** | Nhánh sạch, commit HEAD hợp lệ, không staged changes trái phép | HEAD `2011408`, 0 modified tracked files, 5 untracked docs files chờ Owner duyệt staging | **PASS_WITH_LIMITATIONS** | Non-blocking / Non-blocking / **BLOCKING** | `git status --short`, `git diff --check` |
| **2. Backend Regression** | 100% test suite backend chạy thành công | 471/471 tests PASSED, 0 failed, 0 skipped, 0 xfailed (thời gian 73.49s) | **PASS** | Non-blocking / Non-blocking / Non-blocking | Pytest execution log (`task-5809`) |
| **3. Frontend Build & Typecheck**| TypeScript không lỗi, Vite production build thành công | Typecheck 0 lỗi, Vite build tạo bundle `dist/` thành công sau 5.29s | **PASS** | Non-blocking / Non-blocking / Non-blocking | Frontend build log (`task-5815`) |
| **4. Frontend Test Coverage**| Unit test và Playwright E2E kiểm chứng giao diện | Không có frontend unit test runner; Playwright E2E (`e2e/*.spec.ts`) không chạy để tránh can thiệp live DB | **NOT_RUN** | Non-blocking / **BLOCKING** / **BLOCKING** | `frontend/package.json`, `frontend/e2e/` |
| **5. Authentication** | Đăng ký, đăng nhập JWT, hash mật khẩu an toàn, bảo vệ token | Endpoint `/auth/login` P50=89.51ms (Bcrypt cost), Bearer JWT 30m expire | **PASS** | Non-blocking / Non-blocking / Non-blocking | Phase D1 Raw JSON (`auth_login`), `test_auth.py` |
| **6. Tenant Isolation / RBAC**| Ngăn chặn triệt để cross-tenant data leak và leo quyền | Toàn bộ 9 kịch bản cô lập tenant và phân quyền RBAC đều chặn đứng vi phạm | **PASS** | Non-blocking / Non-blocking / Non-blocking | `tests/test_tenant_isolation.py` (9 tests passed), Phase C Audit |
| **7. Document Ingestion** | Upload, parse, chunk và lưu trữ tài liệu TXT, PDF, DOCX | Cả 3 định dạng hoàn tất E2E trong 331–559 ms, status `ready` | **PASS** | Non-blocking / Non-blocking / Non-blocking | Phase D1 Ingestion (`d1_b_document_ingestion`), Celery logs |
| **8. Celery Broker & Worker**| Worker kết nối Redis broker, nhận và xử lý task bất đồng bộ | Concurrency=2, ping trả về `pong`, không có task lỗi hay backlog tồn đọng | **PASS** | Non-blocking / Non-blocking / Non-blocking | `celery inspect ping`, `scripts/start-worker.sh` |
| **9. Embedding & pgvector** | Vector embedding 384 chiều, tìm kiếm cosine distance `<=>` chính xác | Query encode 29ms, vector search 1.89ms, similarity score đạt 0.8801 | **PASS** | Non-blocking / Non-blocking / Non-blocking | Phase D1 pgvector micro-benchmark, pgvector 0.8.5 |
| **10. RAG & Citations** | Trả lời có trích dẫn nguồn `[Source 1]`, fail-closed khi thiếu context | TTFT 493ms (n=1), câu hỏi hợp lệ trích dẫn chuẩn; 2/3 từ chối do thiếu context | **PASS_WITH_LIMITATIONS** | Non-blocking / Non-blocking / **BLOCKING** | Phase D1 RAG raw JSON, `rag_stream.py` guardrails |
| **11. Agent READ Workflows** | Lập luận multi-step, routing model, gọi công cụ `search_docs` | Model routing overhead 4.8ms, tool latency 88–181ms; độ trễ LLM CPU-bound 68–85s | **PASS_WITH_LIMITATIONS** | Non-blocking / Non-blocking / **BLOCKING** | Runs `a6af0bea`, `5711c490` trong raw JSON D1 |
| **12. Agent WRITE + Approval**| Hành vi ghi phải qua phê duyệt con người, chỉ thực thi sau khi duyệt | Trạng thái `awaiting_approval` hoạt động chuẩn; trace lịch sử chạy 28–66s với status `executed` | **PASS** | Non-blocking / Non-blocking / Non-blocking | `test_agent_approval_security.py`, DB traces `fae6bf8c`, `1491216a` |
| **13. Recovery & SSE Streaming**| Phục hồi lease khi crash, stream sự kiện qua SSE không mất mát | CAS lease claim & renewal hoạt động chính xác; SSE stream đúng lifecycle | **PASS** | Non-blocking / Non-blocking / Non-blocking | `test_reliability_slice_b.py`, `test_rag_stream.py` |
| **14. Security Audit Logging** | Ghi nhận audit trail đầy đủ cho mọi hành động nhạy cảm | Bảng `security_audit_events` (1,692 rows) lưu đầy đủ actor, workspace, action, outcome | **PASS** | Non-blocking / Non-blocking / Non-blocking | `security_audit_events` table query, `test_tenant_isolation.py` |
| **15. Configuration Safety** | Không chứa secrets trong repo, `.env.example` đầy đủ, `.gitignore` an toàn | Không có JWT key hay password thật trong mã nguồn; `.gitignore` bảo vệ data | **PASS** | Non-blocking / Non-blocking / Non-blocking | Kiểm tra `.env.example`, `.gitignore`, `git diff` |
| **16. Database Migrations & Drift**| Schema đồng nhất với migration scripts, không lệch revision | Revision `e2b3c4d50005 (head)`; `alembic check` phát hiện index drifts thứ cấp giữa model và DB | **PASS_WITH_LIMITATIONS** | Non-blocking / Non-blocking / **BLOCKING** | `alembic current`, `alembic heads`, `alembic check` |
| **17. Evidence Reproducibility**| Bằng chứng có mã checksum SHA-256 xác thực, lưu trữ độc lập | Toàn bộ 4 tệp raw artifact được kiểm chứng checksum và lưu trữ lâu dài | **PASS** | Non-blocking / Non-blocking / Non-blocking | `T260029_D1_PERFORMANCE_EVIDENCE_ERRATA.md` |
| **18. Operational Runbook** | Tài liệu hướng dẫn cài đặt, khởi động, dừng, probe và xử lý sự cố | Runbook chi tiết đã được tạo tại `docs/testing/T260029_DEPLOYMENT_RUNBOOK.md` | **PASS** | Non-blocking / Non-blocking / Non-blocking | `docs/testing/T260029_DEPLOYMENT_RUNBOOK.md` |
| **19. Risk Register** | Xác định và phân loại toàn diện các rủi ro kỹ thuật còn tồn đọng | Sổ đăng ký 8 rủi ro cốt lõi với 7 production blockers đã chuẩn hóa | **PASS** | Non-blocking / Non-blocking / Non-blocking | `docs/testing/T260029_RISK_REGISTER.md` |
| **20. Production Limitations** | Minh bạch hóa việc hệ thống chưa đạt chuẩn Production | Tuyên bố miễn trừ không gắn nhãn `PRODUCTION_READY` | **PASS** | Non-blocking / Non-blocking / Non-blocking | Mục 5 trong tài liệu Errata & Báo cáo cuối cùng |

---

## TỔNG HỢP TRẠNG THÁI KIỂM TRA

- **Tổng số cổng kiểm soát:** **20 / 20**.
- **Số cổng đạt yêu cầu (PASS):** **15 / 20** (Cổng 2, 3, 5, 6, 7, 8, 9, 12, 13, 14, 15, 17, 18, 19, 20).
- **Số cổng đạt yêu cầu kèm giới hạn (PASS_WITH_LIMITATIONS):** **4 / 20** (Cổng 1 Git Integrity, Cổng 10 RAG Citations, Cổng 11 Agent READ, Cổng 16 DB Migration Drift).
- **Số cổng chưa chạy (NOT_RUN):** **1 / 20** (Cổng 4 Frontend Playwright E2E Suite).
- **Số cổng bị chặn đối với Local Development Release:** **0 / 20 (KHÔNG CÓ BLOCKER CỤC BỘ)**.
- **Số cổng bị chặn đối với Production Target:** **6 cổng bị chặn** (tương ứng với 7 blockers trong Risk Register: Git Staging, E2E Testing, RAG Quality, Agent Latency, Database Drift, SLA Contract, Soak Testing).
- **Trạng thái sẵn sàng hợp nhất (Merge Readiness):** **`READY FOR REVIEW`** (Chờ quyết định phê duyệt và chỉ đạo staging từ Repository Owner).
