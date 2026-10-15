# Workspace Security & Access Control Architecture (T260024)

## 1. Executive Summary & Mission
Nhiệm vụ của T260024 là nâng cấp **AI Knowledge Lab** từ kiến trúc single-user ownership thành nền tảng **Enterprise Multi-Tenant Knowledge Hub**, hỗ trợ **Secure Workspaces**, **Role-Based Access Control (RBAC)**, **Tenant Data Isolation**, và **Security Audit Trail**.

Mọi tài nguyên tri thức (tài liệu, file upload, chunks, vector embeddings, lịch sử hội thoại AI, citations) được bảo vệ bằng các quy tắc phân quyền nghiêm ngặt thực thi tại backend. Ngay cả khi một người dùng biết chính xác UUID của một tài nguyên thuộc workspace khác, hệ thống phải từ chối truy cập (Fail-Closed).

---

## 2. Security Audit & Current State Analysis

### 2.1 Hiện trạng xác định quyền sở hữu (Before T260024)
- **JWT & Current User**: JWT mang claim `sub: <user_id>`. Dependency `get_current_user` giải mã token, xác thực người dùng trong bảng `users`.
- **Direct User Ownership**:
  - `documents`: gắn trực tiếp `user_id`. Mọi truy vấn đọc/ghi đều lọc `where(Document.user_id == current_user.id)`.
  - `conversations`: gắn trực tiếp `user_id`. Mọi truy vấn đọc/ghi lọc `where(Conversation.user_id == current_user.id)`.
- **Gián tiếp qua Foreign Key**:
  - `document_chunks`: liên kết `document_id -> documents.id`.
  - `messages`: liên kết `conversation_id -> conversations.id`.
  - `message_sources`: liên kết `message_id -> messages.id`.
- **Vector Retrieval**:
  - `search_similar_chunks` thực hiện `JOIN documents ON documents.id == document_chunks.document_id WHERE documents.user_id == user_id`. Việc lọc tenant được thực thi ngay trong SQL query trước khi `LIMIT` và tính toán khoảng cách cosine distance.
- **Celery Ingestion**:
  - `process_document_task(document_id, user_id)` nhận ID và đối chiếu lại với cơ sở dữ liệu trước khi thực thi.

### 2.2 Các ranh giới tin cậy (Trust Boundaries) & Điểm yếu khi chuyển sang Workspaces
1. **Ranh giới Workspace vs User**:
   - Nếu chỉ dựa trên `user_id`, người dùng không thể chia sẻ tài liệu cho đồng nghiệp trong cùng một nhóm/dự án mà không làm lộ dữ liệu cá nhân.
   - Khi chuyển sang Workspace, tài nguyên thuộc về **Workspace**, còn người dùng truy cập thông qua **Membership + Role**.
2. **Nguy cơ IDOR (Insecure Direct Object Reference) & Cross-Tenant Leakage**:
   - Truy vấn tài liệu qua `document_id`: Nếu không kiểm tra `workspace_id` và quyền của user trong workspace đó, kẻ tấn công có thể đoán/thu thập UUID để truy cập trái phép.
   - Vector Similarity Search: Nếu câu truy vấn embedding tìm kiếm trên toàn bảng `document_chunks` mà không ràng buộc `workspace_id`, vector embedding và nội dung đoạn trích sẽ bị rò rỉ giữa các tenant.
   - RAG AI Chat: Nếu conversation không được gắn chặt với workspace, prompt RAG có thể truy xuất context từ workspace A đưa vào câu trả lời cho user tại workspace B.
   - Evidence Viewer: Khi user bấm vào citation để xem chi tiết đoạn nguồn, backend phải kiểm tra user có quyền truy cập vào workspace chứa document đó hay không.
3. **Privilege Escalation**:
   - Người dùng có vai trò VIEWER hoặc EDITOR không được phép tự ý thay đổi vai trò của mình hoặc của người khác.
   - ADMIN không được phép tự nâng cấp thành OWNER hoặc xóa bỏ OWNER cuối cùng của workspace.

---

## 3. Threat Model

| Threat Actor | Capabilities | Attack Vector | Mitigation in T260024 |
| :--- | :--- | :--- | :--- |
| **Malicious Authenticated User (Tenant A)** | Có JWT hợp lệ, biết resource UUID của Tenant B | Gửi API request đọc tài liệu, chunk, conversation của Tenant B (`GET /api/v1/documents/{id}`) | Backend kiểm tra membership và quyền của user trong workspace chứa tài nguyên. Từ chối 404/403. |
| **Curious Member (VIEWER in Workspace A)** | Có quyền VIEWER trong Workspace A | Cố gắng gọi API Upload, Delete, Reprocess document hoặc thay đổi thành viên | RBAC Policy Service kiểm tra quyền cụ thể (`document.create`, `document.delete`, `member.manage`). Chặn 403 Forbidden. |
| **RAG Prompt Injection / Cross-Tenant Retrieval** | Người dùng gửi câu hỏi gợi mở nhằm tìm kiếm tài liệu nhạy cảm của workspace khác | Vector similarity query | SQL JOIN bắt buộc `Document.workspace_id == current_workspace_id` ngay trong mệnh đề WHERE của PostgreSQL vector search. |
| **Worker Context Tampering** | Kẻ tấn công can thiệp vào task payload Celery | Gửi task chứa mismatch `(document_id, workspace_id)` | Worker truy vấn lại DB xác minh quan hệ document - workspace và fencing token trước khi xử lý. |
| **Last Owner Lockout** | Thành viên cố xóa hoặc hạ quyền Owner duy nhất | `DELETE /api/v1/workspaces/{id}/members/{owner_id}` | Logic bảo vệ Last Owner: Từ chối nếu workspace chỉ còn 1 Owner hoạt động. |

---

## 4. RBAC Permission Matrix

Hệ thống định nghĩa 4 vai trò chuẩn:

| Quyền hạn (Permission) | OWNER | ADMIN | EDITOR | VIEWER |
| :--- | :---: | :---: | :---: | :---: |
| `workspace.read` | ✅ | ✅ | ✅ | ✅ |
| `workspace.update` | ✅ | ✅ | ❌ | ❌ |
| `workspace.delete` | ✅ | ❌ | ❌ | ❌ |
| `member.list` | ✅ | ✅ | ✅ | ✅ |
| `member.invite` | ✅ | ✅ | ❌ | ❌ |
| `member.role_change` | ✅ | ❌ | ❌ | ❌ |
| `member.remove` | ✅ | ✅ (Non-Owner) | ❌ | ❌ |
| `document.read` | ✅ | ✅ | ✅ | ✅ |
| `document.create` | ✅ | ✅ | ✅ | ❌ |
| `document.update` | ✅ | ✅ | ✅ | ❌ |
| `document.delete` | ✅ | ✅ | ✅ | ❌ |
| `document.reprocess` | ✅ | ✅ | ✅ | ❌ |
| `chat.read` | ✅ | ✅ | ✅ | ✅ |
| `chat.create` | ✅ | ✅ | ✅ | ✅ |
| `audit.read` | ✅ | ✅ | ❌ | ❌ |

---

## 5. Database Schema & Migration Strategy

### 5.1 Các bảng mới
1. **`workspaces`**:
   - `id`: UUID (PK)
   - `name`: VARCHAR(255)
   - `slug`: VARCHAR(255) UNIQUE
   - `description`: TEXT (nullable)
   - `status`: VARCHAR(30) (active, archived)
   - `created_by`: UUID (FK -> users.id)
   - `created_at`, `updated_at`: TIMESTAMP WITH TIME ZONE
2. **`workspace_memberships`**:
   - `id`: UUID (PK)
   - `workspace_id`: UUID (FK -> workspaces.id, CASCADE)
   - `user_id`: UUID (FK -> users.id, CASCADE)
   - `role`: VARCHAR(30) (owner, admin, editor, viewer)
   - `created_at`, `updated_at`: TIMESTAMP WITH TIME ZONE
   - Unique Constraint: `(workspace_id, user_id)`
3. **`workspace_invitations`**:
   - `id`: UUID (PK)
   - `workspace_id`: UUID (FK -> workspaces.id, CASCADE)
   - `invited_by`: UUID (FK -> users.id)
   - `email`: VARCHAR(320)
   - `role`: VARCHAR(30)
   - `token_hash`: VARCHAR(255)
   - `status`: VARCHAR(30) (pending, accepted, rejected, expired)
   - `expires_at`: TIMESTAMP WITH TIME ZONE
   - `created_at`, `updated_at`: TIMESTAMP WITH TIME ZONE
4. **`security_audit_events`**:
   - `id`: UUID (PK)
   - `workspace_id`: UUID (FK -> workspaces.id, CASCADE)
   - `actor_id`: UUID (FK -> users.id, nullable)
   - `action`: VARCHAR(100)
   - `resource_type`: VARCHAR(50)
   - `resource_id`: UUID (nullable)
   - `outcome`: VARCHAR(20) (success, denied, error)
   - `details`: JSONB (nullable, không chứa bí mật/mật khẩu)
   - `created_at`: TIMESTAMP WITH TIME ZONE

### 5.2 Nâng cấp bảng hiện có (Additive Migration & Safe Backfill)
1. Thêm `workspace_id` vào `documents` (FK -> workspaces.id, ban đầu nullable).
2. Thêm `workspace_id` vào `conversations` (FK -> workspaces.id, ban đầu nullable).
3. **Backfill Script**:
   - Quét qua tất cả `users` hiện tại.
   - Với mỗi user, tự động tạo 1 Personal Workspace (`name="<User Name>'s Workspace"`, `slug="personal-<user_id>"`).
   - Tạo `workspace_memberships` gán user làm `owner`.
   - Update `documents.workspace_id = personal_workspace.id` với mọi document của user.
   - Update `conversations.workspace_id = personal_workspace.id` với mọi conversation của user.
4. Sau khi hoàn tất backfill, áp dụng `ALTER TABLE ... ALTER COLUMN workspace_id SET NOT NULL`.
5. Tạo index trên `(workspace_id)` cho cả `documents` và `conversations`.

---

## 6. Tenant Isolation in RAG & Celery

### 6.1 Vector Similarity Search
Hàm `search_similar_chunks` trong `document_chunk` repository sẽ nhận `workspace_id: UUID` thay cho `user_id: UUID`:
```sql
SELECT document_chunks.*, document_chunks.embedding <=> :query_embedding AS distance, documents.title
FROM document_chunks
JOIN documents ON documents.id = document_chunks.document_id
WHERE documents.workspace_id = :workspace_id
  AND document_chunks.embedding IS NOT NULL
ORDER BY distance
LIMIT :limit;
```
Điều này đảm bảo cơ sở dữ liệu chỉ tính toán và trả về các đoạn trích nằm trong workspace đang truy vấn.

### 6.2 Chat & Streaming SSE
- Endpoint `/api/v1/workspaces/{workspace_id}/rag/ask` và `/ask/stream` kiểm tra membership của người dùng trong `workspace_id` và quyền `chat.create`.
- Conversation được tạo hoặc tải phải có `conversation.workspace_id == workspace_id`.
- Retrieval context sử dụng `workspace_id` để tìm kiếm tài liệu.

### 6.3 Background Celery Jobs
- Payload của task lưu `(document_id, workspace_id, user_id)`.
- Worker truy vấn `get_document_by_id(session, document_id)` và kiểm tra `document.workspace_id == workspace_id`.
- Mọi thao tác chunking, embedding chỉ cập nhật cho document đó.

---

## 7. Implementation Roadmap (3 Vertical Slices)

- **Slice A: Workspace Foundation & Migration**
  - Database models (`Workspace`, `WorkspaceMembership`, `WorkspaceInvitation`, `SecurityAuditEvent`).
  - Migration Alembic + Data Backfill cho users cũ.
  - Core RBAC Policy Service & Dependency Injection (`get_workspace_membership`, `require_permission`).
  - Workspace CRUD & Membership APIs.
  - Tự động tạo Personal Workspace khi user mới đăng ký.
- **Slice B: Tenant Isolation & Security Enforcement**
  - Cập nhật Document APIs & Repositories theo `workspace_id`.
  - Cập nhật Vector Retrieval (`search_similar_chunks`) theo `workspace_id`.
  - Cập nhật Conversation & RAG Streaming APIs theo `workspace_id`.
  - Cập nhật Evidence Viewer & Citations isolation.
  - Cập nhật Celery Ingestion Worker.
  - Bộ kiểm thử bảo mật Adversarial Authorization Tests (Scenarios 1-9).
- **Slice C: Workspace Management, Audit & E2E**
  - Audit Trail Service & Audit Viewer API.
  - Frontend Workspace Switcher trong AppLayout.
  - Frontend Workspace Settings & Member Management UI.
  - Frontend Audit Viewer UI.
  - Playwright E2E Tests đa người dùng & kiểm thử cô lập dữ liệu.
  - Full Regression & Final Report.
