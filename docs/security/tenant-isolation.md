# Cơ Chế Cô Lập Dữ Liệu Tenant (Tenant Data Isolation Architecture)

## 1. Nguyên Tắc Thiết Kế (Core Isolation Principle)

Dữ liệu của một Workspace (bao gồm văn bản tài liệu, các phân đoạn chunks, vector embeddings, nguồn trích dẫn bằng chứng và lịch sử hội thoại) phải được cô lập tuyệt đối. Người dùng thuộc Workspace A không bao giờ có thể đọc, tìm kiếm hoặc nhận trích dẫn từ Workspace B, ngay cả khi câu hỏi có độ tương đồng ngữ nghĩa cực cao với tài liệu của Workspace B.

---

## 2. Kiến Trúc Cô Lập Chi Tiết

### 2.1. Cấu trúc CSDL & Khóa ngoại
- Bảng `workspaces`: Định danh tenant độc lập (`id: UUID`, `is_personal: bool`).
- Bảng `documents`: Có cột `workspace_id: UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`.
- Bảng `conversations`: Có cột `workspace_id: UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`.
- Bảng `security_audit_events`: Có cột `workspace_id: UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`.

### 2.2. Vector Pre-Filter Isolation (Ngăn Chặn Rò Rỉ Embedding)
Trong các hệ thống RAG thông thường, lỗi rò rỉ phổ biến nhất là tìm kiếm Top-K vector trên toàn bộ cơ sở dữ liệu rồi mới lọc kết quả trong Python. Nếu Top-K bị chiếm bởi các chunks của Workspace khác, kết quả có thể bị rỗng hoặc rò rỉ thông tin nhạy cảm.

Trong AI Knowledge Lab:
```sql
SELECT 
    document_chunks.id,
    document_chunks.document_id,
    document_chunks.chunk_index,
    document_chunks.content,
    documents.title AS document_title,
    1 - (document_chunks.embedding <=> :query_embedding) AS similarity
FROM document_chunks
JOIN documents ON document_chunks.document_id = documents.id
WHERE documents.workspace_id = :workspace_id
ORDER BY document_chunks.embedding <=> :query_embedding ASC
LIMIT :limit;
```
**Bảo đảm toán học**: Quá trình tìm kiếm vector chỉ tính khoảng cách trên các vector có `documents.workspace_id == :workspace_id`. Hoàn toàn không bao giờ duyệt qua vector của workspace khác.

### 2.3. Cô Lập Tác Vụ Nền (Celery Cross-tenant Safety)
Khi worker nhận task bất đồng bộ từ message queue Redis:
```python
# Task Ingestion kiểm tra tính toàn vẹn của workspace
if expected_workspace_id is not None and document.workspace_id != expected_workspace_id:
    raise CrossTenantIngestionViolationError("Cross-tenant ingestion rejected.")
```
Nếu có sự không trùng khớp giữa workspace của task và workspace lưu trong database, worker sẽ hủy xử lý ngay lập tức và ghi audit event cảnh báo.

### 2.4. Cô Lập Lịch Sử Hội Thoại & Trích Dẫn (Conversation & Citation Isolation)
- Khi gọi `/api/v1/rag/ask` hoặc `/api/v1/rag/ask/stream`:
  - Kiểm tra `conversation.workspace_id == active_workspace_id`.
  - Nếu conversation thuộc workspace khác, trả về `404 Not Found`.
  - Không cho phép inject tin nhắn hoặc truy vấn trích dẫn xuyên tenant.
