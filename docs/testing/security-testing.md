# Hướng Dẫn Kiểm Thử An Toàn Thông Tin (Security & Isolation Testing)

## 1. Tổng quan Bộ Kiểm Thử An Toàn (Adversarial Security Test Suite)

Tất cả các cơ chế bảo mật của Task T260024 được kiểm chứng tự động thông qua bộ kiểm thử `backend/tests/test_tenant_isolation.py` bao gồm 9 kịch bản tấn công đối kháng (Adversarial Security Scenarios) theo tiêu chuẩn bảo mật doanh nghiệp.

---

## 2. Chi tiết 9 Kịch Bản Đối Kháng (Scenarios 1 -> 9)

### Scenario 1: Cross-tenant Document Access
- **Mục tiêu**: Người dùng Bob thuộc Workspace B cố gắng đọc hoặc tải về tài liệu mật của Alice thuộc Workspace A bằng UUID trực tiếp.
- **Kết quả kỳ vọng**: Hệ thống trả về `404 Not Found` (fail-closed, ngăn chặn ID enumeration).

### Scenario 2: Cross-tenant Vector Search Leakage
- **Mục tiêu**: Alice đưa vào Workspace A một tài liệu chứa chuỗi bí mật đặc biệt (`SECRET_CANARY_STRING_ABC`). Bob trong Workspace B đặt câu hỏi RAG với câu hỏi trùng khớp 100% với bí mật đó.
- **Kết quả kỳ vọng**: RAG pipeline trong Workspace B trả về 0 nguồn trích dẫn từ Workspace A, AI từ chối trả lời hoặc không rò rỉ bất kỳ chunk nào của Workspace A.

### Scenario 3: Cross-tenant Conversation Hijacking
- **Mục tiêu**: Bob cố gắng đọc lịch sử hội thoại của Alice hoặc inject câu hỏi/tin nhắn độc hại vào hội thoại của Alice thông qua `/api/v1/rag/ask`.
- **Kết quả kỳ vọng**: `404 Not Found`.

### Scenario 4: Role-based Ingestion Restriction
- **Mục tiêu**: Thành viên với vai trò `VIEWER` cố gắng tạo tài liệu văn bản hoặc tải file lên workspace.
- **Kết quả kỳ vọng**: `403 Forbidden` ("Insufficient permissions for document.create").

### Scenario 5: Role-based Document Deletion & Reprocess Restriction
- **Mục tiêu**: Thành viên `VIEWER` cố gắng xóa tài liệu hoặc gửi request reprocess vector index.
- **Kết quả kỳ vọng**: `403 Forbidden`.

### Scenario 6: Unauthorized Member Management
- **Mục tiêu**: Thành viên `EDITOR` cố gắng mời thành viên mới, hoặc thăng hạng quyền của chính mình lên Admin/Owner.
- **Kết quả kỳ vọng**: `403 Forbidden`.

### Scenario 7: Last Owner Protection Invariant
- **Mục tiêu**: Owner duy nhất còn lại trong workspace cố tình hạ cấp quyền của mình xuống Editor, hoặc tự xóa/rời khỏi workspace để biến workspace thành vô chủ.
- **Kết quả kỳ vọng**: `400 Bad Request` ("Cannot demote the last owner (only owner) of the workspace").

### Scenario 8: Celery Cross-tenant Ingestion Safety
- **Mục tiêu**: Mô phỏng worker nhận task ingestion có `expected_workspace_id` giả mạo không trùng khớp với `document.workspace_id` trong cơ sở dữ liệu.
- **Kết quả kỳ vọng**: Worker phát hiện vi phạm bảo mật và ngắt xử lý ngay lập tức (`CrossTenantIngestionViolationError`).

### Scenario 9: Audit Trail Integrity & Confidentiality
- **Mục tiêu**: Mọi hành động nhạy cảm (tạo tài liệu, mời thành viên, thay đổi vai trò) đều được ghi nhận vào nhật ký kiểm toán. Thành viên `VIEWER` cố gắng đọc nhật ký kiểm toán này.
- **Kết quả kỳ vọng**: Nhật ký ghi nhận đầy đủ các sự kiện; Viewer bị từ chối với `403 Forbidden`.

---

## 3. Lệnh Thực Thi Bộ Kiểm Thử

Để chạy kiểm thử an toàn thông tin:
```bash
cd backend
.venv/bin/pytest tests/test_tenant_isolation.py -v
```

Để chạy toàn bộ regression suite kiểm tra tính tương thích ngược:
```bash
cd backend
.venv/bin/pytest -q --tb=short
```
Kỳ vọng: **392 passed, 0 failed**.
