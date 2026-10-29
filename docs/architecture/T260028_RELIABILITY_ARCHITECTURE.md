# KIẾN TRÚC VẬN HÀNH & ĐỘ TIN CẬY HỆ THỐNG (T260028)

**Tác giả:** Principal Backend Engineer & Site Reliability Engineer  
**Phiên bản:** 1.0.0  
**Tài liệu tham chiếu:** TASK T260028: Agent Reliability & Production Hardening  

---

## 1. TỔNG QUAN KIẾN TRÚC

Kiến trúc độ tin cậy của **AI Knowledge Lab** nhằm bảo vệ hệ thống khỏi tình trạng kiệt quệ tài nguyên máy chủ cục bộ (CPU, GPU, RAM, VRAM), bảo đảm tính bất biến của dữ liệu khi xảy ra sự cố đột ngột (crash/restart), ngăn chặn triệt để duplicate side effects (đặc biệt các thao tác ghi dữ liệu WRITE) và cung cấp khả năng quan sát vận hành minh bạch.

Hệ thống tái sử dụng hoàn toàn hạ tầng hiện hữu:
- **FastAPI:** Async REST API & SSE Streaming với Correlation IDs Middleware.
- **PostgreSQL 16 + pgvector:** Nguồn sự thật duy nhất (Single Source of Truth), quản lý trạng thái, row-locking (`with_for_update`) và CAS Leases.
- **Redis & Celery:** Rate limiting nguyên tử phân tán và xử lý bất đồng bộ, tự động fallback an toàn sang In-Memory Sliding Window khi Redis offline.
- **Ollama (`qwen3:1.7b`):** Mô hình ngôn ngữ cục bộ được bảo vệ bởi bộ điều phối Concurrency Governor.

---

## 2. QUẢN TRỊ TÀI NGUYÊN & RATE LIMITING (RESOURCE GOVERNANCE)

### 2.1. Distributed Atomic Rate Limiter
- **Thuật toán:** Sliding Window Log sử dụng Redis Sorted Sets (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`, `EXPIRE`) thực thi nguyên tử qua Lua script.
- **Fallback an toàn (Graceful Degradation):** Khi Redis ngắt kết nối hoặc gặp lỗi mạng, bộ điều phối tự động chuyển đổi sang `InMemorySlidingWindowLimiter` (thread-safe, sliding timestamp queue) kèm log cảnh báo, không gây sập ứng dụng (không sinh lỗi HTTP 500).
- **Phân cấp định danh & Hạn mức mặc định:**
  - `auth_login` & `auth_register`: 60 requests / phút theo IP nguồn (chống tấn công brute-force).
  - `rag_ask_user`: 60 requests / phút theo User ID.
  - `rag_ask_workspace`: 120 requests / phút theo Workspace ID.
  - `agent_run_user`: 30 runs / phút theo User ID.
  - `agent_run_workspace`: 60 runs / phút theo Workspace ID.
  - `benchmark_run`: 20 runs / giờ theo Workspace ID.
  - `model_refresh`: 30 requests / phút theo User ID.
- **Chuẩn phản hồi:** Khi vượt hạn mức, trả về `HTTP 429 Too Many Requests` kèm headers chuẩn RFC:
  - `Retry-After`: Số giây còn lại của cửa sổ trượt.
  - `X-RateLimit-Limit`: Ngưỡng tối đa.
  - `X-RateLimit-Remaining`: Số lượt còn lại (bằng `0` khi bị chặn).
  - `X-RateLimit-Reset`: Thời điểm timestamp cửa sổ được làm mới.

### 2.2. Điều tiết Inference Ollama (Inference Concurrency Governor)
- **Vấn đề phần cứng:** GPU NVIDIA GTX 1650 (4 GB VRAM) và CPU cục bộ không thể tải đồng thời nhiều tiến trình suy luận LLM nặng.
- **Admission Control:**
  - `max_concurrency`: Giới hạn tối đa 2 inference chạy đồng thời.
  - `max_queue_size`: Hàng đợi giới hạn tối đa 10 requests đang chờ slot.
  - Nếu hàng đợi vượt quá 10: Từ chối tức thì với mã lỗi `HTTP 503 Service Unavailable` (`detail: Model inference capacity saturated. Queue limit reached.`).
- **Bounded Waiting Timeout:**
  - Thời gian chờ slot tối đa: `ollama_queue_timeout_seconds = 15.0s`.
  - Quá thời gian chờ: Hủy xếp hàng và trả về `HTTP 504 Gateway Timeout`.
- **Quản lý Lease Context Manager:**
  - Mọi lời gọi inference trong RAG Chat Stream, Agent LLM Decision và Model Testing đều được bọc trong `async with inference_governor.acquire():`.
  - Slot và lease token luôn được giải phóng chắc chắn trong khối `finally`, ngăn ngừa tình trạng chiếm giữ slot vĩnh viễn do client disconnect hoặc ngoại lệ đột ngột.

---

## 3. PHỤC HỒI SỰ CỐ & THỰC THI BỀN VỮNG (DURABLE AGENT RECOVERY)

### 3.1. Vòng Đời & Fencing Leases
Vòng đời trạng thái Agent Run:
$$\text{CREATED} \longrightarrow \text{RUNNING} \longleftrightarrow \text{AWAITING\_APPROVAL} \longrightarrow \text{COMPLETED / FAILED / CANCELLED}$$

- **Database-backed Lease:**
  - Cột `lease_token`: Mã định danh duy nhất của worker/tiến trình đang chịu trách nhiệm thực thi.
  - Cột `lease_expires_at`: Thời điểm hết hạn lease (mặc định 60 giây).
  - Cột `last_heartbeat_at`: Thời điểm gia hạn gần nhất.
  - Cột `recovery_attempts`: Đếm số lần phục hồi (tối đa 3 lần).
- **Cơ chế Fencing (Compare-and-Swap):**
  - Worker chỉ có thể nhận quyền chạy nếu `status == 'RUNNING'` và (`lease_token IS NULL` hoặc `lease_expires_at < now` hoặc `lease_token == given_token`).
  - Worker khác hoặc worker cũ (zombie) bị tước quyền không thể commit đè trạng thái.

### 3.2. Safe Recovery Guard (Ngăn Chặn Trùng Lặp Tác Vụ Ghi)
Khi API process hoặc Celery worker bị tắt đột ngột:
1. `AgentRecoveryService` quét các run có `status == 'RUNNING'` và `lease_expires_at < now`.
2. **Quy tắc An Toàn Tuyệt Đối (Safe Recovery Invariant):**
   - **Deadline quá hạn:** Nếu `now >= deadline_at`, chuyển sang `FAILED` (`error_code="execution_timeout"`).
   - **Hết lượt phục hồi:** Nếu `recovery_attempts >= 3`, chuyển sang `FAILED` (`error_code="max_recovery_attempts_exceeded"`).
   - **Bảo vệ thao tác WRITE:** Nếu step cuối cùng đang `PENDING` có thuộc tính `side_effect == 'WRITE'` (ví dụ: tạo tài liệu, xóa tài liệu), hệ thống **tuyệt đối không chạy lại** mà đánh dấu step đó là `FAILED` (`error_code="execution_interrupted"`), tránh tạo ra tài liệu trùng lặp (No duplicate side effects).
   - **Thao tác READ / Khởi đầu:** An toàn để tái thực thi, tăng `recovery_attempts += 1`, giải phóng lease cũ để worker tiếp quản.
   - **AWAITING_APPROVAL:** Trạng thái chờ duyệt không bao giờ bị tự động approve ngầm.

---

## 4. ĐỘ TIN CẬY TRUYỀN DÒNG SỰ KIỆN (SSE RELIABILITY)

- **Hỗ trợ Reconnection Resumption:**
  - Endpoint `GET /api/v1/agent/runs/{run_id}/events` hỗ trợ header chuẩn `Last-Event-ID` hoặc query param `after_seq`.
  - Mỗi event SSE được phát ra theo chuẩn:
    ```
    id: <event_seq>
    event: <event_type>
    data: {...}
    ```
  - Khi trình duyệt hoặc client bị mất kết nối và tự động reconnect, chỉ các sự kiện có `seq > Last-Event-ID` mới được gửi tiếp, không gửi lại các sự kiện cũ.
  - Việc reconnect **không bao giờ** kích hoạt lại tool invocation.
- **Sanitization:** Loại bỏ hoàn toàn raw passwords, JWT access tokens và hidden reasoning khỏi SSE stream.

---

## 5. OBSERVABILITY, READINESS PROBES & DASHBOARD

### 5.1. Correlation IDs & Middleware
- Mọi request HTTP đều được gắn `X-Request-ID` (tái sử dụng từ header client hoặc sinh ngẫu nhiên) và `X-Response-Time-Ms`.
- Mã định danh được liên kết xuyên suốt logs, events và database audit.

### 5.2. Health Probes
- **Liveness (`GET /api/v1/health`):** Xác nhận tiến trình backend đang phản hồi.
- **Readiness (`GET /api/v1/health/ready`):**
  - **Healthy (200):** PostgreSQL OK, Ollama OK.
  - **Degraded (200):** PostgreSQL OK, Ollama unreachable. Toàn bộ tính năng auth, documents, workspaces, search cơ bản vẫn hoạt động bình thường, thông báo cho người dùng chỉ các tính năng AI bị tạm ngừng.
  - **Unhealthy (503):** PostgreSQL không thể kết nối.

### 5.3. Operations Dashboard (`/reliability`)
- Giao diện quản trị vận hành dành riêng cho Workspace OWNER và ADMIN.
- Hiển thị trực quan:
  - Tình trạng sức khỏe 3 thành phần (PostgreSQL, Redis Limiter, Ollama Governor).
  - Tải của Inference Governor: Slots bận, Hàng đợi, Số lượt từ chối quá tải.
  - Nút bấm thủ công "Quét phục hồi Agent Runs" để giải phóng ngay các run bị kẹt.
- **RBAC:** Thành viên cấp VIEWER bị chặn truy cập API vận hành với mã lỗi `HTTP 403 Forbidden`.
