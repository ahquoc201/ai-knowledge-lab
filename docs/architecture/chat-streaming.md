# Kiến trúc Streaming AI Chat & Bảo chứng Trích dẫn (T260022)

## 1. Tổng quan Kiến trúc

Tính năng **Evidence-Driven AI Chat** của hệ thống AI Knowledge Lab cung cấp trải nghiệm hội thoại thời gian thực (real-time conversational assistant) với mô hình cục bộ Ollama (`qwen3:1.7b`), truyền tải phản hồi qua chuẩn Server-Sent Events (HTTP SSE), đồng thời áp dụng nghiêm ngặt các chốt chặn an toàn (reliability guardrails) từ mốc T260020.

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant UI as React Chat Workspace
    participant API as FastAPI Backend (/rag/ask/stream)
    participant PG as PostgreSQL + pgvector
    participant LLM as Ollama (qwen3:1.7b)

    User->>UI: Gửi câu hỏi kèm conversation_id
    UI->>API: POST /api/v1/rag/ask/stream (SSE)
    API->>PG: Lưu tin nhắn User vào DB
    API->>API: Event: retrieval_started
    API->>PG: Vector Similarity Search (pgvector)
    PG-->>API: Trả về Top-K Chunks + Document Metadata
    API->>API: Context Bounding (Tối đa 8000 ký tự)
    API-->>UI: Event: retrieval_completed (Danh sách Sources)

    alt Không có dữ liệu phù hợp (Sources rỗng)
        API-->>UI: Event: token (Thông báo từ chối chuẩn mực)
        API->>PG: Lưu Assistant Refusal Message
        API-->>UI: Event: answer_completed (sources: [])
    else Có dữ liệu trích xuất
        API-->>UI: Event: generation_started
        API->>LLM: Stream Generate với RAG Prompt
        loop Streaming Tokens
            LLM-->>API: Token chunk
            API-->>UI: Event: token (Hiển thị thời gian thực)
        end
        API->>API: Chốt chặn: Kiểm tra Strict Citations ([Source N])
        alt Citations hợp lệ
            API->>PG: Lưu Assistant Message + MessageSources vào DB
            API-->>UI: Event: answer_completed (Answer + Verified Sources)
        else Hallucination / Thiếu Citations
            API->>PG: Lưu Refusal ("Không thể xác minh...") vào DB
            API-->>UI: Event: answer_completed (Override Refusal + sources: [])
        end
    end
```

---

## 2. Các Lifecycle Events của HTTP SSE

Endpoint `POST /api/v1/rag/ask/stream` phát các sự kiện Server-Sent Events theo định dạng:

```http
event: <event_type>
data: {"event": "<event_type>", ...payload}
```

| Event Type | Mục đích | Payload Chính |
| :--- | :--- | :--- |
| `retrieval_started` | Thông báo bắt đầu tìm kiếm vector | `query`, `conversation_id` |
| `retrieval_completed` | Trả về danh sách nguồn được trích xuất | `sources: [{source_index, document_id, document_title, content, similarity, char_start, char_end}]` |
| `generation_started` | Thông báo mô hình LLM bắt đầu suy luận | `{}` |
| `token` | Truyền tải từng token theo thời gian thực | `token: str` |
| `answer_completed` | Kết thúc câu trả lời sau kiểm chứng | `conversation_id`, `message_id`, `answer`, `sources` |
| `error` | Báo lỗi khi xảy ra ngoại lệ runtime | `error: str` |

---

## 3. Hệ thống Guardrails & Bảo chứng Nguồn gốc

1. **No-Context Refusal**: Khi vector search không tìm thấy bất kỳ chunk nào hoặc context rỗng, hệ thống tuyệt đối không gọi LLM để tránh suy diễn vô căn cứ. Câu từ chối chuẩn hóa được phát ngay lập tức:
   > *"Không đủ thông tin trong tài liệu để trả lời câu hỏi này."*
2. **Strict Citation Validation**: Khi mô hình sinh câu trả lời, toàn bộ các khẳng định thực tế phải đi kèm marker `[Source N]`. Nếu mô hình bỏ sót trích dẫn hoặc trích dẫn index không tồn tại, backend kích hoạt fallback an toàn:
   > *"Không thể xác minh câu trả lời từ tài liệu được truy xuất."*
   Đồng thời cơ sở dữ liệu chỉ lưu câu từ chối đã kiểm chứng, không lưu câu trả lời bị hallucinate.
3. **Tenant & User Isolation**: Tất cả câu truy vấn database (từ vector chunk search, messages, conversations) đều bắt buộc lọc theo `user_id` của phiên đăng nhập hiện tại.

---

## 4. Trải nghiệm Người dùng (Frontend Workspace)

- **Interactive Citation Pills**: Trong tin nhắn của trợ lý, các ký hiệu `[Source 1]` được phân tích cú pháp thành các badge tương tác dạng click-to-view.
- **Evidence Panel**: Khi người dùng nhấp vào một trích dẫn, thanh trượt bên phải mở ra hiển thị:
  - Tên tài liệu gốc (`document_title`).
  - Điểm tương đồng cosine (`similarity %`).
  - Vị trí chunk và ký tự (`char_start`, `char_end`).
  - Đoạn trích dẫn nguyên văn với định dạng nổi bật.
- **Quản lý Phiên Hội thoại (Conversation Lifecycle)**: Hỗ trợ tạo mới cuộc trò chuyện, lưu trữ lịch sử tin nhắn, và duyệt lại các phiên hội thoại trong quá khứ kèm đầy đủ bằng chứng.
- **Stop Generation**: Hỗ trợ ngắt kết nối an toàn với `AbortController` khi người dùng nhấn nút dừng.
