# T260039 — Xác minh sản phẩm AI Knowledge End-to-End

Ngày: 2026-11-22 · Nhánh: `feature/T260039`

## 1. Môi trường kiểm chứng (cô lập)

| Thành phần | Cấu hình |
| :--- | :--- |
| PostgreSQL 16 + pgvector | cluster cục bộ `storage/pgdata`, cổng 15432 |
| DB kiểm thử backend | `ailab_t260039_test` (alembic head `f3c4d5e60006`) |
| DB kiểm thử Playwright | `ailab_e2e_test` (alembic head) |
| DB lịch sử `ailab` | **không ghi**; số bản ghi trước/sau giống hệt (users 819, documents 333, chunks 96, workspaces 1259, messages 108) |
| API | uvicorn thật (`app.main:app`) |
| Worker | Celery worker thật (`documents.process`); broker `filesystem://` vì máy không có Redis/Docker |
| Embedding | `intfloat/multilingual-e5-small` thật (CPU) |
| LLM | **MOCK**: HTTP server giả lập giao thức Ollama `/api/chat` (stream + non-stream), trả lời trích xuất từ context kèm `[Source N]`. Ollama thật (`qwen3:1.7b`) có chạy nhưng prefill ~5 token/s trên CPU, nên mọi prompt RAG vượt timeout 60s |

## 2. Hành trình người dùng thật (live stack, 34/34 PASS)

Đăng ký → đăng nhập → `/auth/me` → tạo workspace → upload `.md` → trạng thái `pending → processing → ready` (~2s) → chunks được index → `/rag/ask` (dense mặc định) trả lời
"…18 ngày nghỉ phép… [Source 1]" với `document_id`/`chunk_id` khớp tài liệu đã upload → hội thoại lưu 2 message → `/rag/ask/stream` phát đủ
`retrieval_started → retrieval_completed → model_routed → generation_started → token×N → answer_completed` → follow-up trong cùng hội thoại → hybrid → rerank opt-in (server tắt reranker ⇒ fallback, `rerank_score=null`).

Bảo mật: không token / token sai ⇒ 401; user B: liệt kê/đọc/hỏi trong workspace A ⇒ 403; đọc tài liệu A qua workspace B ⇒ 404; hỏi trong workspace B ⇒ từ chối, 0 nguồn của A; dùng lại `conversation_id` của A ⇒ 404; xoá tài liệu A ⇒ 404.

Lỗi: file `.exe` ⇒ 415 có detail; file rỗng ⇒ `failed` + `error_message="Extracted text is empty"`; câu hỏi ngoài phạm vi ⇒ câu từ chối chuẩn.

## 3. Lỗi xác nhận và bản sửa

| # | Lỗi (tái hiện trên live stack) | Sửa |
| :--- | :--- | :--- |
| D1 | `/rag/ask` trả `500 Internal Server Error` trơn khi LLM sập/timeout; uvicorn đóng kết nối keep-alive nên request kế tiếp của client bị reset | `api/v1/rag.py`: `httpx.HTTPError` ⇒ `503` + `Retry-After` + thông điệp rõ ràng |
| D2 | Sự kiện SSE `error` lộ text nội bộ (URL Ollama) hoặc rỗng `""` khi timeout | `services/rag_stream.py`: `{"error": <thông điệp thân thiện>, "code": llm_unavailable/service_busy/internal_error, "stage"}`; chi tiết ghi log server |
| D3 | Thành viên workspace tiếp tục hội thoại chung qua **stream** ⇒ `message_id: null`, câu trả lời không được lưu (non-stream thì lưu) | Stream lưu message theo phạm vi workspace khi có `workspace_id` (giống non-stream) |
| D4 | Thành viên thấy tài liệu của đồng đội trong danh sách và trong trích dẫn RAG nhưng `GET /documents/{id}` và `/chunks` trả 404 | Đọc tài liệu/chunks theo workspace + quyền `DOCUMENT_READ`; người ngoài vẫn 403/404 |
| D5 | `playwright.config.ts` khởi động backend E2E trên DB lịch sử `ailab` | `E2E_DATABASE_URL`, mặc định `ailab_e2e_test` |

Thay đổi hợp đồng có chủ đích: một assertion cũ trong `test_rag_observability_and_resilience.py` yêu cầu text exception thô xuất hiện trong SSE; nay kiểm tra `code`/`stage`/thông điệp và **cấm** lộ text thô.

## 4. Kết quả kiểm thử tự động

| Bộ | Kết quả |
| :--- | :--- |
| Backend pytest (toàn bộ, DB cô lập) | **589 passed**, 0 failed (4m07s) |
| Test mới `tests/test_product_journey_mvp.py` | 5 passed; trước khi sửa: 3 failed (D1, D2, D4/D3) |
| Ruff `app tests` | sạch |
| Frontend `npm run build` | thành công |
| Playwright (Chromium, `ailab_e2e_test`) | **28 passed** |
| Live journey sau sửa | 34/34; probe lỗi: 503 + SSE `llm_unavailable`; thành viên stream ⇒ message được lưu |

## 5. Khoảng trống MVP còn lại

1. Không có LLM dùng được trên máy dev (CPU quá chậm cho `qwen3:1.7b`), cần GPU/model nhỏ hơn hoặc provider từ xa; chưa xác minh chất lượng trích dẫn của LLM thật.
2. Upload khi broker sập vẫn trả 500 (tài liệu đã đánh dấu `failed`, có thể reprocess); test hiện tại cố ý khẳng định hành vi này.
3. `PATCH/DELETE/reprocess` tài liệu vẫn chỉ dành cho người upload, chưa theo vai trò workspace.
4. Stream gán `llm.model = routed_model` trên provider singleton (`lru_cache`), model định tuyến có thể rò sang request khác.
5. Frontend gọi `DELETE /workspaces/{id}` nhưng backend không có route này.
6. Cold start: request RAG đầu tiên tải embedding model (~14s); chưa warm-up lúc khởi động.
7. Không có Redis/Docker trong WSL, nên chưa chạy được stack chuẩn `compose.yaml` trên máy này.
