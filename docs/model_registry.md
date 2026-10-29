# Model Registry & Capability Discovery (T260027)

Tài liệu thiết kế kiến trúc và vận hành cho Model Registry và Capability Discovery trong **AI Knowledge Lab**.

---

## 1. Mục Tiêu & Nguyên Tắc Thiết Kế

1. **Khám Phá Động (Dynamic Discovery):** Tích hợp trực tiếp với Ollama REST API (`/api/tags`, `/api/ps`, `/api/show`) để phát hiện các mô hình đã cài đặt, thông số kiến trúc, độ dài ngữ cảnh (context length) và trạng thái nạp bộ nhớ (memory/VRAM).
2. **Phân Biệt Năng Lực (Capabilities Verification):**
   - **`ADVERTISED`:** Năng lực được nhà cung cấp hoặc metadata mô hình công bố (ví dụ: cờ `tools`, `completion`, `thinking` trong Ollama show/tags).
   - **`VERIFIED`:** Năng lực đã được chứng minh bằng kiểm nghiệm benchmark thực tế (`AgentBenchmarkRun` với `execution_mode == 'real'` trên đúng phiên bản `model_name` và `model_digest`).
   - **`UNKNOWN`:** Chưa có đủ bằng chứng thực nghiệm để khẳng định.
3. **Cảnh Báo Cỡ Mẫu Thống Kê (Small Sample Size Warning):** Nếu tổng số ca kiểm chuẩn của model nhỏ hơn 30 ca (ví dụ bộ 14 test cases), hệ thống tự động gắn nhãn `has_sufficient_sample_size = False` kèm khuyến cáo sơ bộ, không suy diễn thành độ tin cậy production.
4. **Phát Hiện Thay Đổi Phiên Bản (Digest Drift & Staleness):** Khi model digest thay đổi (người dùng pull lại model mới), hồ sơ benchmark cũ tự động bị đánh dấu `is_stale = True`.

---

## 2. Lược Đồ Cơ Sở Dữ Liệu (Database Schema)

### 2.1. Bảng `model_registry_entries`
- `id` (UUID PK): Khóa định danh duy nhất của mô hình.
- `name` (String, Unique Index): Tên mô hình (VD: `qwen3:1.7b`).
- `digest` (String, Index): Mã băm SHA-256 phiên bản mô hình.
- `provider_type` (String): Mặc định `"ollama"`.
- `is_installed` (Boolean): Trạng thái đã tải về máy cục bộ.
- `is_loaded` (Boolean): Trạng thái đang nạp trên RAM / VRAM (từ `/api/ps`).
- `is_active` (Boolean): Cờ do Quản trị viên kích hoạt hoặc vô hiệu hóa đối với Model Router.
- `parameter_size` (String): Số lượng tham số (VD: `"2.0B"`).
- `quantization_level` (String): Định dạng lượng tử hóa (VD: `"Q4_K_M"`).
- `context_length` (Integer): Độ dài cửa sổ ngữ cảnh tối đa (VD: `40960`).
- `capabilities` (JSON): Trạng thái xác thực năng lực: `{"chat": "verified", "tools": "verified", "thinking": "advertised"}`.
- `metadata_json` (JSON): Chi tiết kiến trúc từ `/api/show`.
- `resource_observations` (JSON): Mức tiêu thụ VRAM và thời gian sống từ `/api/ps`.
- `last_discovered_at` (DateTime): Thời điểm quét phát hiện gần nhất.

### 2.2. Bảng `model_benchmark_profiles`
- `id` (UUID PK): Khóa định danh hồ sơ đánh giá.
- `model_id` (UUID FK -> `model_registry_entries.id`): Liên kết mô hình.
- `model_name`, `model_digest`: Khóa nhận diện phiên bản.
- `benchmark_run_id` (UUID FK -> `agent_benchmark_runs.id`): Liên kết phiên chạy benchmark thực tế của T260026.
- `task_success_rate`, `tool_call_accuracy`, `citation_reference_f1`, `prompt_injection_resistance`, `latency_p50_ms`: Các chỉ số định lượng đo được.
- `has_sufficient_sample_size` (Boolean): Cảnh báo nếu $N < 30$.
- `is_stale` (Boolean): True nếu digest của profile lệch với digest hiện tại của model.

---

## 3. Danh Sách REST APIs

- `GET /api/v1/models`: Danh sách các model trong registry kèm capability badges và latest benchmark profile.
- `POST /api/v1/models/refresh`: Kích hoạt quét Ollama, cập nhật installed/loaded states và đối soát capability verification.
- `GET /api/v1/models/{model_id}`: Xem chi tiết metadata, thông số kiến trúc và resource footprint của một model.
- `PATCH /api/v1/models/{model_id}`: Quản trị viên bật/tắt cờ `is_active` cho model.
- `GET /api/v1/models/{model_id}/benchmarks`: Lịch sử các hồ sơ benchmark và khuyến cáo cỡ mẫu.
