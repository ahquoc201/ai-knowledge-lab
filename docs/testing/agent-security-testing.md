# Báo Cáo Kiểm Thử Bảo Mật Governed AI Agent Runtime (T260025)

## 1. Tổng Thể Kết Quả Kiểm Thử

Hệ thống đã hoàn thành việc kiểm thử tự động toàn diện trên cả Backend (Pytest) và Frontend (Playwright E2E) với tỷ lệ vượt qua **100%**:

- **Tổng số Backend Tests**: **419 / 419 passed** (trong đó có 27 tests chuyên biệt cho Agent Runtime & Security).
- **Tổng số Frontend E2E Tests**: **4 / 4 passed** (kiểm thử đa bước, human approval, rejection, và vai trò viewer).
- **Playwright Navigation Regression Tests**: **2 / 2 passed**.

---

## 2. Chi Tiết 10 Kịch Bản Tấn Công Bảo Mật (Attack Scenarios)

| # | Kịch Bản Tấn Công | Mô Tả & Vector Tấn Công | Cơ Chế Phòng Thủ Của Hệ Thống | Kết Quả Pytest / E2E |
| :-: | :--- | :--- | :--- | :---: |
| **1** | **Malicious Document Injection** | Tài liệu chứa mã độc/lệnh gián tiếp yêu cầu agent thực thi thao tác trái phép. | Dữ liệu tài liệu được bọc trong thẻ `<untrusted_tool_result>`, Policy Enforcer thẩm định độc lập mọi hành động đề xuất. | **PASSED** (`test_agent_policy.py`) |
| **2** | **Fake System Message in Document** | Tài liệu giả mạo `[SYSTEM INSTRUCTION]` tuyên bố override toàn bộ quy tắc bảo mật. | LLM Output Parser chỉ trích xuất JSON schema hợp lệ; Backend bỏ qua mọi tuyên bố vai trò từ prompt. | **PASSED** (`test_agent_llm_parser.py`) |
| **3** | **VIEWER Attempting WRITE Tool** | Người dùng có vai trò `VIEWER` yêu cầu Agent tạo tài liệu mới (`create_workspace_document`). | `AgentPolicyEnforcer` kiểm tra quyền `document.create` phía backend và từ chối thực thi với mã `POLICY_DENIED`. | **PASSED** (`test_agent_orchestrator.py` & E2E) |
| **4** | **Approval Bypass Attempt** | LLM hoặc kẻ tấn công cố tình đưa trường `approved=true` vào câu trả lời JSON. | Backend bỏ qua trường này; trạng thái phê duyệt chỉ được quản lý trong bảng `agent_approval_requests`. | **PASSED** (`test_agent_approval.py`) |
| **5** | **Cross-Tenant Document ID Access** | Kẻ tấn công cung cấp UUID của tài liệu thuộc workspace khác để Agent đọc trộm. | SQL Query tự động ràng buộc `workspace_id = :current_ws`; ném lỗi `TenantBoundaryViolationError`. | **PASSED** (`test_agent_tools.py`) |
| **6** | **Replayed Approval Request** | Kẻ tấn công gửi lại request approve nhiều lần để kích hoạt tạo trùng lặp tài liệu. | Database State Transition kiểm tra trạng thái một chiều (`pending` $\to$ `approved`); chặn đứng double execution. | **PASSED** (`test_agent_approval.py`) |
| **7** | **Role Revocation Mid-Execution** | User khởi tạo với vai trò EDITOR, trong lúc chờ duyệt bị hạ quyền xuống VIEWER. | `AgentApprovalService` tái thẩm định quyền tại thời điểm duyệt (Execution Time) và từ chối ghi dữ liệu. | **PASSED** (`test_agent_orchestrator.py`) |
| **8** | **Infinite Tool Loop / Budget Exceeded** | Model liên tục yêu cầu gọi tool mà không đưa ra câu trả lời cuối cùng. | `AgentOrchestrator` áp đặt giới hạn `max_steps` (8) và `max_tool_calls` (10); tự động ngắt và đánh dấu `FAILED`. | **PASSED** (`test_agent_orchestrator.py`) |
| **9** | **Malformed / Hallucinated Tool Call** | Model gọi tool không tồn tại hoặc truyền payload sai schema cú pháp. | Bounded repair retry (tối đa 2 lần); nếu thất bại sẽ từ chối và thông báo lỗi rõ ràng. | **PASSED** (`test_agent_llm_parser.py`) |
| **10** | **Sensitive Info in Audit Trail** | Agent truy xuất tài liệu chứa mật khẩu/token hoặc nội dung văn bản nhạy cảm. | `AgentAuditService` khử trùng (sanitize), loại bỏ trường `content` thô, chỉ lưu trữ `document_id`, `title`, và metadata bounded. | **PASSED** (`test_agent_audit.py`) |

---

## 3. Nhật Ký Thực Thi Kiểm Thử Thực Tế

### Backend Test Suite (Pytest)
```bash
cd backend && DATABASE_URL='postgresql+asyncpg://ailab:local_only_change_me@/ailab?host=/tmp&port=15432' .venv/bin/python -m pytest -q --tb=short
........................................................................ [ 17%]
........................................................................ [ 34%]
........................................................................ [ 51%]
........................................................................ [ 68%]
........................................................................ [ 85%]
..............................................................           [100%]
419 passed, 3 warnings in 118.42s (0:01:58)
```

### Frontend E2E Test Suite (Playwright)
```bash
cd frontend && node node_modules/@playwright/test/cli.js test e2e/agent.spec.ts --reporter=list
Running 4 tests using 1 worker

  ✓  1 …T260025) › hiển thị Agent Workspace và form khởi tạo nhiệm vụ mới (2.0s)
  ✓  2 …ụ đa bước với Policy Enforcement và Human Approval cho WRITE tool (1.7s)
  ✓  3 …25) › từ chối phê duyệt (Rejection) ngăn chặn thực thi WRITE tool (1.4s)
  ✓  4 … vai trò VIEWER bị cảnh báo giới hạn quyền và không thể phê duyệt (2.3s)

4 passed (21.5s)
```
