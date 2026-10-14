# Mô Hình Đe Dọa Bảo Mật (Threat Model) - Secure Workspaces & Tenant Isolation

## 1. Tổng quan & Phạm vi (Scope)

Tài liệu này xác định các rủi ro an ninh thông tin, bề mặt tấn công và mô hình phòng vệ đa tầng cho nền tảng **AI Knowledge Lab** theo chuẩn phân loại **STRIDE** (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) tập trung vào tính năng Secure Multi-Tenant Workspaces (Task T260024).

---

## 2. Phân tích STRIDE & Các Vector Tấn công

| Mối đe dọa (Threat) | Vector Tấn công thực tế | Giải pháp Phòng thủ (Mitigation) | Vị trí thực thi |
| :--- | :--- | :--- | :--- |
| **Spoofing** (Giả mạo) | Kẻ tấn công gửi header `X-Workspace-Id` của workspace mà họ không phải thành viên. | Dependency `get_active_workspace_membership` xác thực quan hệ giữa `current_user.id` và `workspace_id` trong bảng `workspace_members`. Nếu không tìm thấy, từ chối ngay với `403 Forbidden` hoặc `404 Not Found`. | `backend/app/api/deps.py` |
| **Tampering** (Can thiệp trái phép) | Người dùng Viewer cố ý gửi request `POST /api/v1/documents` hoặc `DELETE /api/v1/documents/{id}`. | RBAC permission dependency `require_workspace_permission("document.create")` chặn ngay tại tầng API route. Viewer không thể ghi hoặc xóa. | `backend/app/api/v1/documents.py` |
| **Repudiation** (Chối bỏ trách nhiệm) | Người dùng quản trị xóa tài liệu nhạy cảm hoặc thay đổi vai trò người khác rồi chối bỏ hành động. | Hệ thống ghi nhật ký bất biến `security_audit_events` (không có API update/delete audit log). Lưu chi tiết `actor_id`, `actor_email`, `action`, `resource_id`, `ip_address` và timestamp UTC. | `backend/app/services/audit.py` |
| **Information Disclosure** (Rò rỉ thông tin) | Vector Search trả về chunks của Workspace khác do chỉ lọc cosine distance mà không filter workspace. | **Pre-filter Vector SQL JOIN**: `search_similar_chunks` JOIN `Document` và kiểm tra `Document.workspace_id == workspace_id` trực tiếp trong mệnh đề `WHERE` trước `ORDER BY distance LIMIT k`. Tuyệt đối không filter ở tầng application memory. | `backend/app/repositories/document_chunk.py` |
| **Denial of Service** (Từ chối dịch vụ) | Owner tự xóa mình khỏi workspace khiến workspace trở thành vô chủ (orphaned workspace). | **Last Owner Protection**: Kiểm tra số lượng Owner còn lại trong workspace; nếu `<= 1` sẽ chặn hoàn toàn các thao tác Demote, Remove hoặc Leave (`400 Bad Request`). | `backend/app/services/membership.py` |
| **Elevation of Privilege** (Leo thang đặc quyền) | Thành viên Editor tự gửi request thăng hạng bản thân lên Admin/Owner. | Chặn tự đổi role của chính mình (`actor.id == target_user_id`). Áp dụng ma trận phân cấp bậc quản lý vai trò `can_manage_target_role`. | `backend/app/services/membership.py` |

---

## 3. Kiến trúc Phòng thủ Đa tầng (Defense in Depth)

Hệ thống tuân thủ nguyên lý không tin tưởng một tầng duy nhất:

```
[ Client Request ]
       │
       ▼ (Layer 1: Gateway / Route Guard)
[ JWT Authentication & Active Workspace Verification ]
  - Verify user signature
  - Verify workspace membership
       │
       ▼ (Layer 2: RBAC Permission Evaluation)
[ Role-Based Permissions (Fail-Closed) ]
  - OWNER, ADMIN, EDITOR, VIEWER check
       │
       ▼ (Layer 3: Service & Logic Invariants)
[ Business Logic & Protection Invariants ]
  - Last Owner Protection
  - Document-Workspace Ownership Binding
       │
       ▼ (Layer 4: Data Layer Pre-Filter)
[ Database SQL Pre-Filter ]
  - Document query: WHERE workspace_id = :ws_id
  - Vector similarity: JOIN documents ON chunks.document_id = documents.id
                       WHERE documents.workspace_id = :ws_id
       │
       ▼ (Layer 5: Asynchronous Worker Safety)
[ Celery Ingestion Validation ]
  - Task validates document.workspace_id == expected_workspace_id
  - Abort immediately if mismatched
```

---

## 4. Chính sách Fail-Closed & Zero Data Leakage

1. **Không có Workspace Header**: Mặc định hệ thống an toàn tự động fallback về **Personal Workspace** của người dùng hiện tại, ngăn ngừa rò rỉ dữ liệu ngoài ý muốn.
2. **Không phân quyền**: Mặc định từ chối (`403 Forbidden`). Không bao giờ cấp quyền mặc định mở.
3. **Truy cập tài nguyên chéo tenant**: Khi một người dùng truy cập ID tài liệu, hội thoại hoặc tin nhắn thuộc workspace khác, hệ thống trả về `404 Not Found` (thay vì 403) để ngăn chặn tấn công thăm dò sự tồn tại của ID (ID enumeration attack).
