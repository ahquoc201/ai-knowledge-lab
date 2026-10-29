# Adaptive Model Routing & Reliability Architecture (T260027)

## 1. Overview & Objectives

Hệ thống **Adaptive Model Routing** chịu trách nhiệm tự động phân loại yêu cầu công việc (Task Taxonomy), đánh giá các ứng viên mô hình ngôn ngữ dựa trên các cổng bảo mật nghiêm ngặt (Security Hard Gates), tính điểm toán học minh bạch (Explainable Scoring Formulation) và thực thi điều phối với cơ chế dự phòng an toàn (Bounded Reliability Fallback).

---

## 2. Task Taxonomy (7 Loại Tác Vụ)

Hệ thống xác định 7 loại tác vụ chuẩn hóa cho RAG Chat và Governed Agent Runtime:

1. **`SIMPLE_CHAT`**: Hội thoại thông thường hoặc giải đáp kiến thức tổng quát không có tài liệu truy xuất từ workspace.
2. **`RAG_FACTUAL_QA`**: Trả lời câu hỏi có trích dẫn từ 1 đoạn tài liệu trích xuất chính xác.
3. **`RAG_MULTI_DOCUMENT_SYNTHESIS`**: Tổng hợp, so sánh thông tin đa nguồn (từ $\ge 2$ tài liệu).
4. **`STRUCTURED_EXTRACTION`**: Trích xuất dữ liệu có cấu trúc (JSON schema, key-value).
5. **`AGENT_TOOL_SELECTION`**: Agent tự động phân tích và chọn tool đọc/truy vấn thích hợp.
6. **`AGENT_MULTI_STEP_WORKFLOW`**: Kế hoạch tuần tự nhiều bước, kiểm soát bước thực thi liên tục.
7. **`AGENT_WRITE_PROPOSAL`**: Tạo hoặc sửa đổi dữ liệu (yêu cầu Human Approval nếu có side effects).

---

## 3. Security Hard Gates

Trước khi tính điểm chất lượng, bất kỳ ứng viên mô hình nào cũng phải vượt qua toàn bộ các cổng chặn bảo mật độc lập:

- **Installed & Active Gate**: Mô hình phải thực sự được cài đặt trong môi trường và không bị Admin vô hiệu hóa.
- **Tenant Allowlist Gate**: Mô hình phải nằm trong danh sách được cấp phép (`allowed_models`) của Workspace Routing Policy.
- **Zero Actual Data Leakage Gate**: Nếu benchmark đo được `actual_data_leakage_rate > 0.0`, mô hình bị loại ngay lập tức.
- **Tenant Isolation Gate**: Tỷ lệ thành công phân lập tenant `tenant_isolation_success` phải đạt $100\%$ ($1.0$).
- **Capability Verification Gate**: Đối với tác vụ sử dụng tool (`AGENT_TOOL_SELECTION`, `AGENT_MULTI_STEP_WORKFLOW`, `AGENT_WRITE_PROPOSAL`), mô hình bắt buộc phải có capability `tools` đã được xác minh hoặc kiểm chứng.

---

## 4. Explainable Scoring Formulation

Điểm số ứng viên được tính toán minh bạch theo công thức:

$$\text{Score} = w_{\text{qual}} \cdot \text{QualityScore} + w_{\text{tool}} \cdot \text{ToolAccuracy} - w_{\text{lat}} \cdot \text{LatencyPenalty} + \text{ColdStartBonus}$$

Trong đó:
- **`QualityScore`**: Tỷ lệ thành công tác vụ đo được từ benchmark (`task_success_rate`).
- **`ToolAccuracy`**: Độ chính xác gọi tool (`tool_call_accuracy`).
- **`LatencyPenalty`**: $\min(1.0, \frac{\text{Latency P50}}{30000\text{ms}})$.
- **`ColdStartBonus`**: $+0.1$ nếu mô hình hiện đang nạp sẵn trong RAM/VRAM (`is_loaded=True`).

---

## 5. Bounded Reliability Fallback

- Khi mô hình được chọn gặp sự cố vận hành (Ollama timeout, connection reset, context overflow):
  - Hệ thống tự động kích hoạt `fallback_chain` đã được sắp xếp theo thứ tự điểm số của các mô hình đủ điều kiện.
  - Số lần thử fallback bị giới hạn bởi `max_fallback_attempts` (mặc định: 2).
  - Không bao giờ bypass Workspace RBAC, Policy Enforcement, hay Human Approval trong chuỗi fallback.

---

## 6. Observability & Audit Trail

Mỗi quyết định điều phối được ghi vết trong bảng `model_routing_decisions`:
- `task_type`: Loại tác vụ.
- `selected_model`: Mô hình được chọn.
- `candidate_evaluations`: Đầy đủ danh sách ứng viên, điểm số và lý do chấp nhận/loại trừ.
- `fallback_occurred`: Cờ đánh dấu đã phục hồi qua fallback.
- `latency_ms`: Thời gian xử lý routing decision.
- `context_metadata`: Tuyệt đối không lưu prompt thô hay nội dung tài liệu bảo mật.
