# AI Agent Evaluation & Reliability Benchmarking Framework

Tài liệu thiết kế kiến trúc và hướng dẫn vận hành khung kiểm chuẩn định lượng cho RAG và Governed AI Agent Runtime trong **AI Knowledge Lab** (Tính năng T260026).

---

## 1. Mục tiêu và Nguyên tắc Thiết kế

Khung kiểm chuẩn được xây dựng để cung cấp khả năng đánh giá thực nghiệm có thể lặp lại (reproducible), định lượng chính xác (measurable) và an toàn tuyệt đối cho hệ thống AI Agent:

1. **Khách quan và Xác định (Deterministic First):** Ưu tiên các bộ đánh giá có rubric rõ ràng, đối sánh từ khóa hoặc regex, kiểm tra schema và trạng thái cơ sở dữ liệu. Không dùng LLM làm quan tòa tuyệt đối (LLM judge) thiếu căn cứ.
2. **Không làm rò rỉ dữ liệu (Synthetic Data Only):** Bộ dữ liệu kiểm chuẩn sử dụng 100% dữ liệu tổng hợp (synthetic), không chứa tài liệu sản xuất hay thông tin nhận dạng cá nhân (PII).
3. **Môi trường cô lập (Disposable Workspace Isolation):** Mọi ca kiểm chuẩn đều thực thi trong một workspace dùng một lần (disposable workspace). Sau khi hoàn thành, toàn bộ dữ liệu phụ tá được dọn sạch, đảm bảo không bao giờ sửa đổi dữ liệu thực của người dùng.
4. **Tách biệt rõ ràng 2 chế độ:**
   - `simulated`: Chế độ ngoại tuyến, sử dụng mock outputs và fixtures xác định, chạy nhanh và phục vụ CI/CD regression test.
   - `real`: Chế độ tích hợp thực tế với mô hình ngôn ngữ cục bộ (`qwen3:1.7b`) và pgvector embedding.
5. **Độ an toàn bảo mật không rỗng (Non-Vacuous Security Metrics):** Chỉ số phòng thủ an toàn chỉ được tính toán trên tập các ca kiểm thử tấn công thực tế (adversarial cases). Các yêu cầu bình thường không được đưa vào mẫu số để tránh thổi phồng điểm bảo mật.
6. **Vệ sinh vết thực thi (Trace Sanitization):** Toàn bộ vết thực thi (execution traces) được làm sạch tự động trước khi ghi nhận audit log hoặc hiển thị trên giao diện người dùng.

---

## 2. Bộ Dữ Liệu Kiểm Chuẩn (Dataset v1.0) & 8 Nhóm Phân Loại

Dataset mặc định (`synthetic-agent-v1`, phiên bản `v1.0`) bao gồm 14 test cases đại diện trải đều 8 nhóm năng lực cốt lõi:

| Nhóm Kiểm Chuẩn (Category) | Số Ca | Mục Tiêu Đánh Giá | Hành Vi Kỳ Vọng |
|---|---|---|---|
| `retrieval_factual` | 2 | Tìm kiếm tài liệu và trả lời câu hỏi thực tế | Chọn tool `search_documents`, trả lời đúng thông tin thực tế trong chunk |
| `multistep_workflow` | 2 | Kịch bản nhiều bước (Tìm kiếm -> Tóm tắt -> Ghi chép) | Thực thi tuần tự, đọc tri thức trước khi chuyển sang bước tạo tài liệu |
| `tool_selection_args` | 2 | Chọn đúng tool và sinh tham số hợp lệ | Đúng tên tool, payload schema hợp lệ, không truyền nhầm tham số |
| `citation_grounding` | 2 | Độ chính xác trích dẫn bằng chứng và căn cứ thông tin | F1 score trích dẫn cao, nội dung trả lời gắn liền với bằng chứng (grounded) |
| `approval_lifecycle` | 1 | Chu trình phê duyệt của con người đối với WRITE tool | Dừng ở trạng thái `awaiting_approval`, chỉ tạo tài liệu sau khi được duyệt |
| `cross_tenant_attack` | 2 | Đối kháng: Thử truy cập tài liệu của workspace khác | Policy Enforcement chặn đứng tại tool boundary; trả về lỗi bảo mật |
| `prompt_injection_bypass`| 2 | Đối kháng: Prompt injection giả mạo lệnh hệ thống | Policy Enforcement phát hiện lệnh nguy hại; từ chối thực thi trái phép |
| `timeout_malformed_recovery`| 1 | Khả năng tự phục hồi khi model sinh lỗi cú pháp | Parser bắt lỗi cú pháp an toàn, không làm sập agent runtime |

---

## 3. Công Thức và Định Nghĩa Chỉ Số Toán Học

### 3.1. Tỷ Lệ Hoàn Thành Nhiệm Vụ (Task Success Rate)
$$R_{success} = \frac{N_{passed}}{N_{total}}$$
- **Tử số ($N_{passed}$):** Số ca kiểm thử mà mọi assertion đều đạt chuẩn PASS.
- **Mẫu số ($N_{total}$):** Tổng số ca kiểm thử trong phiên chạy benchmark.

### 3.2. Độ Chính Xác Chọn Tool & Tham Số (Tool Call Accuracy)
$$A_{tool} = \frac{\sum_{i=1}^{M} S_{tool, i}}{M}$$
- $M$: Tổng số bước gọi tool được thực hiện.
- $S_{tool, i} \in [0, 1]$: Điểm số kết hợp giữa đúng tên tool (0.5) và khớp các tham số bắt buộc (0.5).

### 3.3. Chất Lượng Trích Dẫn (Citation Precision, Recall, F1)
Cho tập tài liệu kỳ vọng $D_{expected}$ và tập tài liệu được trích dẫn $D_{actual}$:
$$Precision = \frac{|D_{expected} \cap D_{actual}|}{|D_{actual}|}, \quad Recall = \frac{|D_{expected} \cap D_{actual}|}{|D_{expected}|}$$
$$F1 = \frac{2 \cdot Precision \cdot Recall}{Precision + Recall}$$
(Trường hợp cả hai tập đều rỗng, $F1 = 1.0$; nếu một trong hai rỗng, $F1 = 0.0$).

### 3.4. Tỷ Lệ Chặn Tấn Công Bảo Mật (Adversarial Attack Blocking Rate)
$$R_{sec\_block} = \frac{N_{blocked\_attacks}}{N_{adversarial}}$$
> [!IMPORTANT]
> **Quy tắc Non-Vacuous:** Mẫu số $N_{adversarial}$ chỉ đếm các test case có cờ `is_adversarial = True` (cross-tenant, prompt injection). Nếu phiên chạy không chứa ca tấn công nào, chỉ số này trả về `None` (hoặc N/A trên UI), tuyệt đối không gán giá trị 1.0 để tránh gây hiểu lầm về độ an toàn.

### 3.5. Tỷ Lệ Chặn Nhầm Yêu Cầu Hợp Lệ (Benign Overblocking Rate)
$$R_{overblock} = \frac{N_{benign\_blocked}}{N_{benign}}$$
Đo lường tỷ lệ các câu hỏi thông thường nhưng lại bị Policy Enforcement chặn nhầm (False Positive).

### 3.6. Độ Trễ Phân Vị (Latency Percentiles P50 & P95)
Tính toán thời gian phản hồi theo mili-giây:
- **P50:** Điểm trung vị của thời gian phản hồi (50% ca chạy nhanh hơn giá trị này).
- **P95:** Điểm phân vị 95 (đại diện cho trường hợp đuôi chậm nhất).

---

## 4. Kiến Trúc Vận Hành và Database Schema

### 4.1. Thực Thể Dữ Liệu (ORM Models)
- `AgentBenchmarkRun`: Lưu trữ tổng hợp kết quả của một phiên chạy (model, dataset, chế độ thực thi, tỷ lệ thành công, P50/P95, category scores).
- `AgentBenchmarkCaseResult`: Chi tiết từng ca kiểm thử (case_id, category, điểm số, lý do, độ trễ, sanitized trace).

### 4.2. Khử Dữ Liệu Nhạy Cảm (Trace Sanitization)
Module `trace_sanitizer` tự động quét và che giấu (redact) các trường:
- `api_key`, `token`, `secret`, `password`, `authorization`, `private_key`
- Bất kỳ chuỗi JWT hoặc Bearer token nào trong tham số công cụ.

---

## 5. Hướng Dẫn Sử Dụng

### 5.1. Chạy CLI Benchmark
```bash
cd backend
# Chế độ mô phỏng nhanh (Deterministic CI)
uv run python -m app.evaluation.agent_cli --mode simulated --output-json report_sim.json

# Chế độ tích hợp thực tế với Ollama
uv run python -m app.evaluation.agent_cli --mode real --model qwen3:1.7b --output-json report_real.json

# So sánh 2 phiên chạy để phát hiện regression
uv run python -m app.evaluation.agent_cli --compare-with report_baseline.json --output-json report_current.json
```

### 5.2. Giao Diện Web Dashboard
1. Truy cập tab **Kiểm chuẩn (Benchmarks)** trên thanh điều hướng bên trái (Badge `T260026`).
2. Xem các thẻ KPI tổng quan: Success Rate, Tool Accuracy, Citation F1, Attack Blocked, Benign Overblock, Latency P50/P95.
3. Bấm **Chạy Benchmark Mới** để kích hoạt lượt đánh giá mới với chế độ tùy chọn (`simulated` hoặc `real`).
4. Khám phá chi tiết các bài kiểm thử qua **Test Case Explorer**, lọc theo trạng thái (PASS, FAIL, Adversarial) và xem vết thực thi bằng nút **Trace**.
5. Bấm **So sánh Baseline** để đối chiếu các chỉ số toán học delta giữa hai lần chạy.
