# Chính Sách Phân Quyền (RBAC Policy & Permission Matrix)

## 1. Định nghĩa Vai trò (Workspace Roles)

Hệ thống AI Knowledge Lab hỗ trợ 4 vai trò phân cấp trong mỗi Workspace:

1. **OWNER (Chủ sở hữu)**: Toàn quyền quản trị workspace, quản lý tài liệu, quản lý thành viên, xem audit trail, thay đổi cài đặt workspace hoặc xóa workspace.
2. **ADMIN (Quản trị viên)**: Quản lý tài liệu, mời và quản lý thành viên (với vai trò thấp hơn hoặc bằng Editor), xem nhật ký kiểm toán. Không thể xóa workspace hoặc thay đổi Owner.
3. **EDITOR (Biên tập viên)**: Thêm mới, cập nhật, reprocess và xóa tài liệu trong workspace. Khởi tạo hội thoại và hỏi đáp với AI Assistant.
4. **VIEWER (Người xem)**: Chỉ xem tài liệu, xem thông tin thành viên, hỏi đáp với AI Assistant dựa trên kho tri thức sẵn có của workspace. **Bị cấm hoàn toàn mọi hành vi tải lên, cập nhật hoặc xóa tài liệu.**

---

## 2. Ma trận Quyền hạn (Permission Matrix)

| Quyền hạn (Action) | Quyền cụ thể (Permission Key) | OWNER | ADMIN | EDITOR | VIEWER |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Workspace Info** | `workspace.read` |  |  |  |  |
| **Cập nhật Workspace** | `workspace.update` |  |  | ❌ | ❌ |
| **Xóa Workspace** | `workspace.delete` |  *(Non-personal)* | ❌ | ❌ | ❌ |
| **Rời Workspace** | `workspace.leave` |  *(Non-last owner)* |  |  |  |
| **Xem Tài liệu** | `document.read` |  |  |  |  |
| **Tạo / Tải lên Tài liệu** | `document.create` |  |  |  | ❌ |
| **Cập nhật / Reprocess** | `document.update` |  |  |  | ❌ |
| **Xóa Tài liệu** | `document.delete` |  |  |  | ❌ |
| **Tạo Hội thoại / Hỏi RAG** | `conversation.create` |  |  |  |  |
| **Xem Hội thoại / Chi tiết** | `conversation.read` |  |  |  |  |
| **Xóa Hội thoại** | `conversation.delete` |  |  |  |  |
| **Xem Danh sách Thành viên** | `member.read` |  |  |  |  |
| **Mời Thành viên mới** | `member.invite` |  |  | ❌ | ❌ |
| **Cập nhật Vai trò** | `member.role_update` |  |  *(Lên Editor/Viewer)* | ❌ | ❌ |
| **Xóa Thành viên** | `member.remove` |  |  *(Editor/Viewer)* | ❌ | ❌ |
| **Xem Audit Trail** | `audit.read` |  |  | ❌ | ❌ |

---

## 3. Quy tắc Bảo vệ Owner Cuối cùng (Last Owner Invariant)

Nhằm đảm bảo mỗi workspace luôn có ít nhất một người chịu trách nhiệm quản trị:

- **Demote Restriction**: Nếu một Workspace chỉ còn duy nhất 1 thành viên có vai trò `OWNER`, bất kỳ nỗ lực hạ cấp vai trò của thành viên này sẽ bị từ chối với lỗi `400 Bad Request` ("Cannot demote the last owner (only owner) of the workspace").
- **Remove / Leave Restriction**: Chủ sở hữu cuối cùng không thể tự rời hoặc bị xóa khỏi workspace (`400 Bad Request`: "Cannot remove or leave as the last owner (only owner) of the workspace").
- **Personal Workspace Protection**: Workspace cá nhân (`is_personal = true`) không thể bị xóa và chủ sở hữu không thể rời khỏi.
