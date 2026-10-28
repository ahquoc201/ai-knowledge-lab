# Kiến Trúc Governed AI Agent Runtime (T260025)

## 1. Tổng Quan & Triết Lý Thiết Kế

Hệ thống **Governed AI Agent Runtime** được thiết kế để cung cấp khả năng tự chủ (agentic autonomous execution) cho Large Language Models (LLMs) trong môi trường doanh nghiệp đa người dùng, đa không gian làm việc (multi-tenant workspace).

Khác với các chatbot hội thoại thông thường hoặc các agent framework mã nguồn mở tự do (thường tin cậy mù quáng vào quyết định của LLM), Governed Agent Runtime tuân thủ triết lý:

> **"LLM proposes, Backend disposes, Humans supervise."**
> (LLM đề xuất hành động, Backend thực thi thẩm định độc lập, Con người giám sát phê duyệt tác vụ ghi dữ liệu).

```
                      +-----------------------------+
                      |   User / Client UI / SSE    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      Agent Orchestrator     |
                      |   (Bounded Execution Loop)  |
                      +--------------+--------------+
                                     |
           +-------------------------+-------------------------+
           |                         |                         |
           v                         v                         v
+--------------------+    +--------------------+    +--------------------+
|  Agent State Mach. |    |    LLM Adapter     |    |   Tool Registry    |
| (Database-Backed)  |    |  (Ollama/DeepSeek) |    |  (Typed Contracts) |
+--------------------+    +--------------------+    +---------+----------+
                                                              |
                                                              v
                                                    +--------------------+
                                                    |  Policy Enforcer   |
                                                    | (Identity & RBAC)  |
                                                    +---------+----------+
                                                              |
                                             +----------------+----------------+
                                             |                                 |
                                             v (READ_ONLY: Allowed)            v (WRITE: Side-Effect)
                                   +--------------------+            +--------------------+
                                   |   Tool Executor    |            |  Approval Service  |
                                   | (Workspace Scoped) |            | (Human-in-the-Loop)|
                                   +---------+----------+            +---------+----------+
                                             |                                 |
                                             +----------------+----------------+
                                                              |
                                                              v
                                                    +--------------------+
                                                    | Execution Auditor  |
                                                    | (Sanitized Events) |
                                                    +--------------------+
```

---

## 2. Vòng Lặp Thực Thi Độc Lập (Bounded Execution Loop)

Agent không chạy một vòng lặp `while True` vô tận. Thay vào đó, mỗi Agent Run được quản lý bởi `AgentOrchestrator` với các rào chắn ngân sách thực thi nghiêm ngặt:

1. **Ngân sách số bước (`max_steps`)**: Mặc định 8 bước, tối đa 20 bước. Khi vượt quá ngân sách bước, Agent Run chuyển sang trạng thái `FAILED` với mã `BUDGET_EXCEEDED`.
2. **Ngân sách lượt gọi công cụ (`max_tool_calls`)**: Mặc định 10 lượt gọi. Chặn đứng các tình huống model bị kẹt trong vòng lặp vô hạn gọi tool liên tục.
3. **Ngưỡng chặn vi phạm Policy liên tiếp (`max_consecutive_denials`)**: Tối đa 3 lần từ chối liên tiếp từ Policy Enforcement. Nếu model liên tục cố tình gọi các tool trái quyền hoặc truy vấn tài nguyên ngoài workspace, hệ thống ngắt tác vụ ngay lập tức.
4. **Thời gian thực thi tối đa (Timeout Budget)**: Mặc định 300 giây (5 phút). Run sẽ bị timeout nếu vượt quá thời hạn.
5. **Giới hạn số lần sửa lỗi cấu trúc (`max_repair_retries`)**: Tối đa 2 lần retry nếu model sinh ra chuỗi JSON sai schema cú pháp.

---

## 3. Máy Trạng Thái Của Agent (Agent State Machine)

Máy trạng thái được định nghĩa trong `app/core/agent_state.py` và lưu trữ bền vững (persistent) vào cơ sở dữ liệu PostgreSQL.

```
       +--------------+
       |   CREATED    |
       +-------+------+
               |
               v
       +--------------+  WRITE Tool Requiring Approval
       |   RUNNING    | --------------------------------> +--------------------+
       +-------+------+                                   | AWAITING_APPROVAL  |
          |    |   ^                                      +---------+----------+
          |    |   |                Approved & Resumed              |
          |    |   +------------------------------------------------+
          |    |
          |    +------------------------+ (All Steps Done / Final Answer)
          |                             |
          v (Policy Denied/Budget/Err)  v
+--------------------+        +--------------------+
|       FAILED       |        |     COMPLETED      |
+--------------------+        +--------------------+
          ^                             ^
          |                             |
          +--------------+--------------+
                         | (User Cancellation)
                  +------+-------+
                  |  CANCELLED   |
                  +--------------+
```

### Các chuyển đổi trạng thái hợp lệ (`VALID_TRANSITIONS`):
- `CREATED` $\to$ `RUNNING`, `CANCELLED`
- `RUNNING` $\to$ `AWAITING_APPROVAL`, `COMPLETED`, `FAILED`, `CANCELLED`
- `AWAITING_APPROVAL` $\to$ `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`
- `COMPLETED` $\to$ (Trạng thái kết thúc - Terminal State)
- `FAILED` $\to$ (Trạng thái kết thúc - Terminal State)
- `CANCELLED` $\to$ (Trạng thái kết thúc - Terminal State)

Bất kỳ nỗ lực chuyển trạng thái bất hợp pháp nào (ví dụ từ `COMPLETED` sang `RUNNING`) đều bị chặn bởi ngoại lệ `InvalidStateTransitionError` và ghi log cảnh báo bảo mật.

---

## 4. Mô Hình Lưu Trữ Bền Vững (Database Schema)

Hệ thống sử dụng SQLAlchemy Async và Alembic migration (`a7c3e9d10001_create_agent_runtime_tables.py`) để tạo 4 bảng dữ liệu:

### 4.1. Bảng `agent_runs`
- `id` (UUID, Primary Key): Định danh duy nhất của lượt chạy.
- `workspace_id` (UUID, Foreign Key `workspaces.id`, Index): Không gian làm việc sở hữu tác vụ (buộc cách ly tenant).
- `initiated_by` (UUID, Foreign Key `users.id`): Người dùng xác thực đã khởi chạy tác vụ.
- `goal` (Text): Yêu cầu người dùng giao cho agent.
- `status` (Enum `AgentRunStatus`): Trạng thái hiện tại (`created`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`).
- `current_step` (Integer): Số bước đã hoàn thành.
- `max_steps` (Integer): Ngân sách bước tối đa.
- `max_tool_calls` (Integer): Ngân sách gọi tool tối đa.
- `tool_call_count` (Integer): Số tool đã gọi thực tế.
- `consecutive_denials` (Integer): Số lần bị từ chối quyền liên tiếp.
- `allowed_tools` (JSONB): Danh sách whitelist công cụ được phép dùng trong lượt chạy này.
- `final_answer` (Text): Câu trả lời cuối cùng tổng hợp cho người dùng.
- `sources` (JSONB): Danh sách tài liệu tham chiếu và trích dẫn bằng chứng.
- `error_message` (Text): Thông tin lỗi đã được làm sạch nếu tác vụ thất bại.
- `created_at`, `updated_at`, `completed_at`: Timestamps ghi nhận tiến độ.

### 4.2. Bảng `agent_steps`
- `id` (UUID, Primary Key): Định danh bước thực thi.
- `run_id` (UUID, Foreign Key `agent_runs.id`, Cascade Delete).
- `step_number` (Integer): Thứ tự bước thực thi ($1, 2, 3\dots$).
- `thought` (Text): Suy luận nội bộ của agent trước khi hành động.
- `tool_name` (String): Tên công cụ được đề xuất gọi.
- `arguments` (JSONB): Tham số truyền vào cho công cụ.
- `status` (Enum `AgentStepStatus`): Trạng thái bước (`running`, `succeeded`, `denied`, `failed`, `awaiting_approval`, `rejected`).
- `result` (JSONB): Kết quả trả về từ công cụ (hoặc thông báo lỗi sanitized).
- `created_at`, `completed_at`: Thời gian thực hiện bước.

### 4.3. Bảng `agent_approval_requests`
- `id` (UUID, Primary Key): Mã yêu cầu phê duyệt.
- `run_id` (UUID, Foreign Key `agent_runs.id`).
- `step_id` (UUID, Foreign Key `agent_steps.id`).
- `tool_name` (String): Tên công cụ WRITE đề xuất.
- `proposed_arguments` (JSONB): Dữ liệu chi tiết tham số ghi.
- `payload_hash` (String): Mã băm SHA-256 bảo vệ tính toàn vẹn của payload.
- `status` (Enum `ApprovalStatus`): `pending`, `approved`, `rejected`, `expired`.
- `decided_by` (UUID, Foreign Key `users.id`): Người ra quyết định phê duyệt.
- `decided_at` (DateTime): Thời điểm ra quyết định.
- `decision_reason` (Text): Ghi chú xác thực kiểm duyệt.
- `expires_at` (DateTime): Hạn chót phê duyệt (15 phút sau khi tạo).

### 4.4. Bảng `agent_execution_events`
- `id` (UUID, Primary Key): Mã sự kiện runtime.
- `run_id` (UUID, Foreign Key `agent_runs.id`).
- `seq` (Integer): Số thứ tự sự kiện tuần tự để phục vụ Server-Sent Events (SSE) streaming.
- `event_type` (String): `run_created`, `step_started`, `tool_call_proposed`, `policy_checked`, `approval_required`, `step_completed`, `run_completed`, `run_failed`.
- `payload` (JSONB): Dữ liệu sự kiện đã được khử trùng thông tin nhạy cảm.
- `created_at` (DateTime): Thời điểm phát sinh sự kiện.

---

## 5. Danh Mục Công Cụ (Tool Contracts & Tool Registry)

Mọi công cụ được quản lý tập trung tại `app/services/agent_tools.py` theo giao ước phân loại rõ ràng:

| Tên Công Cụ | Phân Loại | Quyền Yêu Cầu | Yêu Cầu Duyệt? | Chức Năng |
| :--- | :--- | :--- | :--- | :--- |
| `search_workspace_documents` | `READ_ONLY` | `document.read` | Không | Tìm kiếm ngữ nghĩa vector trong workspace |
| `get_document_details` | `READ_ONLY` | `document.read` | Không | Đọc chi tiết nội dung và metadata tài liệu |
| `create_workspace_document` | `WRITE` | `document.create` | **Bắt buộc** | Tạo tài liệu mới trong workspace hiện tại |

Mọi công cụ đều có:
- Pydantic schema kiểm soát chặt chẽ kiểu dữ liệu đầu vào.
- Timeout độc lập ngăn ngừa treo worker.
- Cơ chế xử lý tenant filter tự động ép buộc từ `workspace_id` của phiên xác thực người dùng.
