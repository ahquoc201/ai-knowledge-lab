# T260029 — SỔ ĐĂNG KÝ RỦI RO PHÁT HÀNH (RELEASE RISK REGISTER)
**Dự án:** AI Knowledge Lab
**Mã tài liệu:** `T260029-RISK-REGISTER`
**Nhánh áp dụng:** `feature/T260029`
**Ngày lập:** 2026-11-09
**Cơ sở kế thừa:** Phase C Audit, Phase D1 Benchmark & D1 Errata

---

## 1. NGUYÊN TẮC QUẢN TRỊ RỦI RO PHÁT HÀNH

Mọi rủi ro và giới hạn kỹ thuật được phân định rõ ràng theo 3 cấp độ đích phát hành:
- **Local Development Target:** Dành cho lập trình viên phát triển tính năng cục bộ.
- **Staging Candidate Target:** Dành cho môi trường tích hợp và kiểm chuẩn tiền sản xuất.
- **Production Target:** Yêu cầu đáp ứng SLA, tính sẵn sàng cao, bảo mật tải đồng thời và mở rộng đa máy chủ.

---

## 2. BẢNG CHI TIẾT CÁC RỦI RO ĐÃ XÁC NHẬN

### Nhóm A: Rủi ro Bảo mật & Độ tin cậy (Security & Reliability)

#### RISK-SR-01: Bộ điều phối suy luận chưa kiểm chứng bão hòa tải sống (Live Governor Saturation)
- **Bằng chứng (Evidence):** Unit tests kiểm chứng logic 503/504 bằng mock/semaphore giả lập (`test_reliability_slice_a.py`). Chưa có kịch bản dồn tải trực tiếp làm sập live Uvicorn pool.
- **Mức độ nghiêm trọng (Severity):** Medium (P2)
- **Tác động (Impact):** Khi nhiều người dùng gửi prompt đồng thời vượt quá `max_concurrency=2` và `max_queue_size=10`, hàng đợi có thể nghẽn và phát sinh timeout.
- **Biện pháp giảm thiểu (Mitigation):** Client áp dụng Exponential Backoff; cấu hình timeout rõ ràng (`OLLAMA_QUEUE_TIMEOUT_SECONDS=15.0`).
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING** (Cần chạy load test k6 trong Staging)
  - Production: **BLOCKING** (Bắt buộc kiểm chứng live load trước khi public)
- **Quyết định từ Owner:** Cần phê duyệt kế hoạch Stress Test tại môi trường Staging.

#### RISK-SR-02: Bộ giới hạn Rate-Limit 429 chưa kiểm thử cạn kiệt trực tiếp trên tải sống
- **Bằng chứng (Evidence):** Kịch bản kiểm thử dựa trên unit test và mã Lua sliding window. Trong live benchmark D1, request rate chỉ đạt ~18.9 RPS (dưới ngưỡng trần).
- **Mức độ nghiêm trọng (Severity):** Low (P3)
- **Tác động (Impact):** Người dùng có thể gặp phản hồi 429 khi thao tác nhanh liên tục.
- **Biện pháp giảm thiểu (Mitigation):** Đã có header `Retry-After` và `X-RateLimit-*`; frontend cần hiển thị thông báo đếm ngược thân thiện.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING**
  - Production: **NON-BLOCKING**
- **Quyết định từ Owner:** Chấp thuận cấu hình trần mặc định (60 req/phút/user).

#### RISK-SR-03: Kiểm thử phục hồi Celery Worker Crash dựa trên trạng thái Lease mô phỏng
- **Bằng chứng (Evidence):** Kiểm thử phục hồi tự động dựa trên thời gian hết hạn lease (`lease_expires_at`) và CAS state trong DB (`test_processing_lease_recovery.py`), chưa thực hiện gửi tín hiệu `SIGKILL` vật lý vào tiến trình Celery worker đang ingest.
- **Mức độ nghiêm trọng (Severity):** Medium (P2)
- **Tác động (Impact):** Nếu tiến trình worker bị OOM killer tiêu diệt giữa chừng, tài liệu có thể duy trì trạng thái `processing` cho tới khi hết hạn lease (5 phút).
- **Biện pháp giảm thiểu (Mitigation):** Cơ chế định kỳ quét tài liệu mồ côi (`reprocess_stale_documents`) đã được kiểm chứng hoạt động chính xác.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING**
  - Production: **BLOCKING** (Cần kiểm chứng Chaos Engineering trên Kubernetes)
- **Quyết định từ Owner:** Chấp thuận cơ chế lease-based recovery cho bản release hiện tại.

#### RISK-SR-04: Inference Governor mang tính chất cục bộ theo tiến trình (Process-Local Boundary)
- **Bằng chứng (Evidence):** Governor khởi tạo semaphore trong bộ nhớ tiến trình FastAPI (`asyncio.Semaphore(2)`).
- **Mức độ nghiêm trọng (Severity):** High (P1)
- **Tác động (Impact):** Khi scale-out backend lên $N$ Uvicorn workers, số lượng request đồng thời gửi tới Ollama sẽ là $N \times 2$, có nguy cơ làm sập daemon suy luận Ollama duy nhất.
- **Biện pháp giảm thiểu (Mitigation):** Ở môi trường hiện tại, chỉ chạy duy nhất 1 tiến trình Uvicorn. Khi scale-out, phải chuyển Governor sang Redis Distributed Semaphore.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING** (Do chỉ chạy 1 worker)
  - Staging: **NON-BLOCKING** (Nếu chạy 1 worker)
  - Production: **BLOCKING** (Bắt buộc tái cấu trúc sang Distributed Governor trước khi scale-out)
- **Quyết định từ Owner:** Ghi nhận kiến trúc này là giới hạn cố hữu của T260028, chuyển sang nhiệm vụ tiếp theo để nâng cấp phân tán.

---

### Nhóm B: Rủi ro Hiệu năng (Performance Risks)

#### RISK-PF-01: Suy luận LLM trên CPU chi phối >99% thời gian phản hồi
- **Bằng chứng (Evidence):** Phase D1 ghi nhận Ollama `qwen3:1.7b` đạt ~11.85 tokens/giây trên CPU Intel i5. Non-streaming RAG mất P50 = 10.84s; Agent READ mất 68s – 85s cho 2 vòng lặp ReAct.
- **Mức độ nghiêm trọng (Severity):** High (P1)
- **Tác động (Impact):** Người dùng phải chờ đợi lâu khi sử dụng tính năng Agent và Non-streaming RAG.
- **Biện pháp giảm thiểu (Mitigation):** Ưu tiên sử dụng Streaming RAG qua SSE (TTFT ~493 ms để hiển thị kết quả dần dần); cấu hình tăng timeout lên 180s.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING**
  - Production: **BLOCKING** (Bắt buộc trang bị GPU chuyên dụng có VRAM $\ge$ 16GB)
- **Quyết định từ Owner:** Chấp nhận trải nghiệm hiện tại trên máy dev cục bộ.

#### RISK-PF-02: Chưa có văn bản Hợp đồng Thỏa thuận Mức độ Dịch vụ (SLA/SLO) được phê duyệt
- **Bằng chứng (Evidence):** Không tồn tại văn bản quy định ngưỡng trễ trong repository. Mọi số liệu D1 chỉ là baseline nội bộ.
- **Mức độ nghiêm trọng (Severity):** Medium (P2)
- **Tác động (Impact):** Thiếu căn cứ pháp lý để khẳng định hệ thống đạt hay không đạt chuẩn sản xuất.
- **Biện pháp giảm thiểu (Mitigation):** Báo cáo minh bạch các số liệu đo lường thô mà không tự phong nhãn "Production Ready".
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING**
  - Production: **BLOCKING** (Cần Product Owner phê duyệt SLA trước khi GO-LIVE)
- **Quyết định từ Owner:** Product Owner cần ban hành văn bản SLA/SLO cho v1.0.

#### RISK-PF-03: Hành vi rò rỉ bộ nhớ dài hạn chưa được kiểm chứng (Unverified Memory Leak)
- **Bằng chứng (Evidence):** Benchmark D1 chỉ kéo dài 4.5 phút với ~30 requests. Áp lực bộ nhớ tăng 3.05 GB sau khi nạp model.
- **Mức độ nghiêm trọng (Severity):** Medium (P2)
- **Tác động (Impact):** Có rủi ro tích tụ bộ nhớ hoặc rò rỉ connection pool nếu chạy liên tục nhiều tuần.
- **Biện pháp giảm thiểu (Mitigation):** Khởi động lại worker theo chu kỳ (Celery `max-tasks-per-child=100`); giám sát Prometheus/Grafana.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING**
  - Staging: **NON-BLOCKING**
  - Production: **BLOCKING** (Bắt buộc chạy Soak Test tối thiểu 24 giờ)
- **Quyết định từ Owner:** Lên kế hoạch kiểm thử ngâm tải ở Phase Staging Hardening.

---

### Nhóm C: Rủi ro Chất lượng Truy xuất RAG (RAG Retrieval Quality)

#### RISK-RQ-01: Tỷ lệ từ chối trả lời quan sát được là 66.7% trong kiểm chuẩn D1
- **Bằng chứng (Evidence):** Trong 3 câu hỏi non-streaming RAG tại D1, 2 câu trả lời bị Guardrail từ chối (`sources_count = 0`), chỉ 1 câu trả lời trích xuất thành công (`sources_count = 3`).
- **Mức độ nghiêm trọng (Severity):** High (P1)
- **Tác động (Impact):** Hệ thống thà từ chối trả lời còn hơn bịa đặt (hallucination) khi độ tương đồng ngữ nghĩa của chunks không vượt qua ngưỡng. Tuy nhiên, tỷ lệ từ chối cao làm giảm trải nghiệm người dùng nếu tài liệu chưa được chia nhỏ tối ưu.
- **Biện pháp giảm thiểu (Mitigation):** Không nới lỏng guardrails bảo mật một cách tùy tiện. Cải thiện chiến lược chunking (kích thước chunk 500-1000 ký tự có overlap 200) và tối ưu câu prompt tìm kiếm.
- **Phân loại Blocker:**
  - Local Dev: **NON-BLOCKING** (Hành vi Fail-Closed bảo vệ an toàn thông tin)
  - Staging: **NON-BLOCKING**
  - Production: **BLOCKING** (Bắt buộc đo đạc F1 và Recall trên tập dữ liệu chuẩn > 100 câu hỏi)
- **Quyết định từ Owner:** Giữ nguyên chính sách Fail-Closed an toàn, không nới lỏng guardrails.

---

## 3. MA TRẬN PHÂN LOẠI BLOCKER THEO TARGET PHÁT HÀNH

| Risk ID | Tên rủi ro | Mức độ | Local Dev Target | Staging Target | Production Target |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **RISK-SR-01**| Live Governor Saturation | P2 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-SR-02**| Live Rate Limiter 429 | P3 | Non-blocking | Non-blocking | Non-blocking |
| **RISK-SR-03**| Physical Worker Crash | P2 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-SR-04**| Process-Local Governor | P1 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-PF-01**| CPU LLM Inference Latency | P1 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-PF-02**| Lack of Approved SLA/SLO | P2 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-PF-03**| Unverified Memory Leak | P2 | Non-blocking | Non-blocking | **BLOCKING** |
| **RISK-RQ-01**| RAG 66.7% Refusal Rate | P1 | Non-blocking | Non-blocking | **BLOCKING** |

**KẾT LUẬN QUẢN TRỊ:**
- **Đối với mục tiêu Local Development Release:** **KHÔNG CÓ BLOCKER**. Hệ thống hoàn toàn sẵn sàng cho môi trường phát triển cục bộ.
- **Đối với mục tiêu Production Release:** Tồn tại **7 Blockers cốt lõi** (RISK-SR-01, RISK-SR-03, RISK-SR-04, RISK-PF-01, RISK-PF-02, RISK-PF-03, RISK-RQ-01) cần được giải quyết ở các giai đoạn sau (Staging Load Test, GPU Offload, Distributed Governor, Soak Test, SLA Definition, RAG Quality Benchmark).
