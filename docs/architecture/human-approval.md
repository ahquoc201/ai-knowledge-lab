# Quy Trình Phê Duyệt Con Người Trong Vòng Lặp (Human-in-the-Loop Approval)

## 1. Mục Đích & Nguyên Lý

Để ngăn ngừa các sự cố phá hoại dữ liệu, ghi đè thông tin trái phép hoặc rò rỉ kiến thức do Agent thực hiện, hệ thống thiết lập một quy trình phê duyệt tách biệt hoàn toàn khỏi luồng tự động của LLM.

Mọi công cụ được phân loại là **`WRITE`** (có side-effect làm biến đổi trạng thái hệ thống) đều **bắt buộc phải có sự chấp thuận rõ ràng của con người** (Human Approval) trước khi được thực thi.

---

## 2. Vòng Đời Phê Duyệt (Approval Lifecycle)

```
[Agent đề xuất WRITE Tool]
             |
             v
[Backend xác định công cụ yêu cầu Approval]
             |
             v
[Tạo AgentApprovalRequest (status=pending, hash SHA-256)]
             |
             v
[Chuyển AgentRun sang AWAITING_APPROVAL & Tạm dừng thực thi]
             |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
     [User Approve qua UI]                           [User Reject qua UI]
             |                                               |
             v                                               v
[Tái thẩm định quyền hạn (Re-check RBAC)]      [Cập nhật status=rejected]
             |                                               |
             +---------------+                               v
             |               |                 [Agent ghi nhận Rejection]
             v [Hợp lệ]      v [Mất quyền]                   |
     [Thực thi Tool]    [Từ chối thực thi]                   v
             |               |                 [Hoàn tất Run với Final Answer]
             v               v
     [Audit Trail]      [Audit Warning]
             |               |
             +---------------+
             |
             v
[Chuyển trạng thái AgentRun sang RUNNING/COMPLETED]
```

---

## 3. Cấu Trúc Yêu Cầu Phê Duyệt & Chống Giả Mạo (Payload Integrity)

Mỗi yêu cầu phê duyệt được bảo vệ bởi hàm băm mật mã:

$$\text{payload\_hash} = \text{SHA-256}(\text{canonical\_json}(\text{arguments}))$$

### Các trường dữ liệu bắt buộc:
1. `id` (UUID): Mã định danh duy nhất của yêu cầu phê duyệt.
2. `run_id` & `step_id`: Liên kết cứng với lượt chạy và bước thực thi cụ thể.
3. `tool_name`: Tên công cụ dự kiến thực thi (ví dụ `create_workspace_document`).
4. `proposed_arguments`: Toàn bộ tham số mà Agent đề xuất.
5. `payload_hash`: Đảm bảo payload không bị sửa đổi giữa thời điểm đề xuất và thời điểm con người bấm duyệt.
6. `expires_at`: Thời điểm hết hạn phê duyệt (mặc định 15 phút). Sau thời gian này, yêu cầu tự động chuyển sang `EXPIRED`.
7. `status`: `pending` $\to$ `approved` / `rejected` / `expired`.

---

## 4. Các Rào Chắn Bảo Mật (Security Guards)

### 4.1. Chống Tấn Công Replay (Anti-Replay Attack)
- Một `AgentApprovalRequest` chỉ có thể được phê duyệt một lần duy nhất.
- Chuyển trạng thái được bảo vệ bởi giao dịch cơ sở dữ liệu (Database Transaction Isolation). Khi một yêu cầu đã ở trạng thái `approved` hoặc `rejected`, bất kỳ cuộc gọi API tiếp theo nào đều bị từ chối với lỗi `ApprovalAlreadyDecidedError`.

### 4.2. Chống Đổi Quyền Trong Quá Trình Chờ Duyệt (Role Revocation Mid-Execution)
- Nếu người khởi tạo tác vụ bị giáng cấp từ `EDITOR` xuống `VIEWER` trong lúc tác vụ đang tạm dừng chờ duyệt:
  - Khi lệnh phê duyệt được gửi tới Backend, `AgentApprovalService` gọi `AgentPolicyEnforcer.verify_permission()` để kiểm tra lại quyền thực tế tại thời điểm T1 (Execution Time).
  - Backend phát hiện người dùng không còn quyền `document.create`, hủy bỏ thao tác ghi, ghi nhật ký cảnh báo bảo mật và chuyển Agent Run sang trạng thái kết thúc an toàn mà không có bất kỳ dữ liệu nào bị ghi vào cơ sở dữ liệu.

### 4.3. Kiểm Soát Quyền Của Người Phê Duyệt (Approver Authorization)
- Chỉ những người dùng có quyền hợp lệ đối với workspace (tối thiểu `EDITOR` hoặc `ADMIN`/`OWNER`) mới có thể bấm nút Phê duyệt.
- Tài khoản ở vai trò `VIEWER` trên giao diện sẽ thấy nút Phê duyệt bị vô hiệu hóa (disabled) kèm dòng cảnh báo: *"Tài khoản Viewer không có quyền thực thi WRITE tool. Bạn chỉ có thể từ chối."*
