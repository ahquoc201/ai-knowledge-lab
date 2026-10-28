# Chính Sách Bảo Mật & Thực Thi Thẩm Quyền Độc Lập (Agent Tool Policy)

## 1. Nguyên Tắc Cốt Lõi: Độc Lập Khỏi Mô Hình LLM

Một trong những sai lầm phổ biến nhất trong các ứng dụng AI Agent hiện nay là **tin tưởng vào output do LLM sinh ra**. Trong hệ thống AI Knowledge Lab, LLM được định nghĩa là **"Untrusted Intent Generator"** (Bộ sinh ý đồ chưa được xác thực).

> **Nguyên tắc vàng:**
> Mô hình ngôn ngữ lớn (LLM) không có quyền tự quyết định thẩm quyền của mình. LLM chỉ có thể **đề xuất** hành động (Proposal).
> Lớp **Policy Enforcement** độc lập phía Backend (`AgentPolicyEnforcer`) là cơ quan duy nhất có thẩm quyền quyết định cho phép hoặc từ chối hành động.

```
       +---------------------------------------------+
       |   LLM Generated Response (Untrusted Input)   |
       |   "Call create_workspace_document(title=...)"|
       +----------------------+----------------------+
                              |
                              v
       +---------------------------------------------+
       |     AgentPolicyEnforcer (Backend AuthZ)     |
       |  1. Principal Authentication Check          |
       |  2. Workspace Membership Verification       |
       |  3. RBAC Permission Check (e.g. doc.create) |
       |  4. Tenant Boundary Enforcement             |
       |  5. Tool Allowlist Validation               |
       |  6. Human Approval Lifecycle Check          |
       +----------------------+----------------------+
                              |
             +----------------+----------------+
             |                                 |
             v [Denial]                        v [Allowed]
+--------------------------+     +--------------------------+
| Block Action             |     | Execute Tool / Request   |
| Record Audit Violation   |     | Human Approval           |
+--------------------------+     +--------------------------+
```

---

## 2. Quy Trình Thẩm Định 6 Lớp Phía Backend

Trước khi bất kỳ công cụ nào được chuyển giao cho `AgentToolExecutor`, `AgentPolicyEnforcer` thực hiện tuần tự 6 bài kiểm tra:

### 2.1. Xác thực Danh tính Khởi tạo (Identity Binding)
- Mỗi `AgentRun` được liên kết chặt chẽ và bất biến với `initiated_by` (UUID của người dùng đăng nhập qua JWT) và `workspace_id`.
- Agent không bao giờ có thể giả mạo danh tính của người dùng khác hay chuyển quyền sang tài khoản Service Account có quyền hạn cao hơn.

### 2.2. Kiểm tra Tư cách Thành viên Workspace (Membership Verification)
- Backend kiểm tra trong cơ sở dữ liệu xem `user_id` có còn là thành viên hoạt động (`WorkspaceMember`) của `workspace_id` hay không.
- Nếu người dùng đã bị xóa khỏi workspace, mọi tác vụ của agent lập tức bị chấm dứt với trạng thái `FAILED`.

### 2.3. Kiểm tra Quyền Hạn Dựa trên Vai Trò (Workspace RBAC)
Hệ thống đối chiếu vai trò của người dùng với quyền yêu cầu của công cụ:
- Vai trò `VIEWER`: Chỉ có quyền `document.read`. Bất kỳ yêu cầu gọi WRITE tool nào (như `create_workspace_document`) đều bị từ chối ngay lập tức với mã lỗi `POLICY_DENIED`.
- Vai trò `EDITOR`: Có quyền `document.read` và `document.create`. Được phép đề xuất WRITE tool, nhưng phải qua bước Human Approval.
- Vai trò `ADMIN` / `OWNER`: Có đầy đủ quyền đọc, ghi và quản lý workspace.

### 2.4. Ràng buộc Ranh giới Tenant Cưỡng bức (Tenant Boundary Enforcement)
- **Tuyệt đối không sử dụng tham số `workspace_id` do LLM tạo ra**: Backend ép buộc gán `workspace_id` từ phiên chạy đã được xác thực vào mọi truy vấn database.
- Khi truy xuất tài liệu theo ID (`get_document_details`), Backend kiểm tra chéo: `SELECT * FROM documents WHERE id = :doc_id AND workspace_id = :authenticated_workspace_id`. Nếu tài liệu thuộc workspace khác, hệ thống ném ngoại lệ `TenantBoundaryViolationError`.

### 2.5. Danh mục Cho Phép Của Lượt Chạy (Tool Allowlist Validation)
- Mỗi lượt chạy có một danh sách công cụ được phép (`allowed_tools`). Nếu LLM tự ý gọi một công cụ nằm ngoài danh sách được cấp phép ban đầu, yêu cầu sẽ bị từ chối ngay lập tức.

### 2.6. Tái thẩm định Quyền Hạn tại Thời điểm Thực thi (Permission Re-check)
- Khi một hành động ghi được đưa ra chờ duyệt, người dùng có thể mất hàng giờ trước khi phê duyệt.
- Nếu trong khoảng thời gian đó, người dùng bị hạ quyền từ `EDITOR` xuống `VIEWER`, Backend sẽ **kiểm tra lại quyền hạn tại chính thời điểm nhận được lệnh phê duyệt**.
- Nếu phát hiện quyền không còn hợp lệ, Backend từ chối thực thi tác vụ ghi, hủy bỏ phê duyệt và chuyển Agent Run sang trạng thái lỗi.

---

## 3. Chống Các Hình Thức Giả Mạo & Bỏ Qua Phê Duyệt

| Hình thức tấn công | Cơ chế phòng thủ của Governed Agent |
| :--- | :--- |
| LLM sinh `approved=true` trong câu trả lời JSON | Backend bỏ qua hoàn toàn trường này; trạng thái phê duyệt chỉ được quản lý trong bảng `agent_approval_requests` thông qua API xác thực riêng biệt của con người. |
| Prompt injection yêu cầu agent đọc workspace khác | Bộ lọc tenant ở tầng cơ sở dữ liệu (PostgreSQL tenant filter) cưỡng bức lọc theo `workspace_id` của phiên xác thực. |
| Người dùng Viewer yêu cầu LLM tạo tài liệu | Policy Enforcer chặn đứng trước khi tool được thực thi; thông báo lỗi được ghi nhận và trả về cho agent. |
| Replay lại token hoặc ID phê duyệt cũ | Bảng approval kiểm tra trạng thái chuyển đổi `pending -> approved/rejected` một chiều (idempotency & state machine). |
