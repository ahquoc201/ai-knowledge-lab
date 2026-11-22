# T260040: Tích hợp LLM thật và cô lập request

Ngày: 2026-11-22 · Nhánh: `feature/T260040` (tách từ `feature/T260039`, vì nhánh đó chưa merge vào `main`)

## 1. Môi trường

| Thành phần | Cấu hình |
| :--- | :--- |
| Máy | Intel i5-10500H (6 nhân/12 luồng, AVX2), 11.6 GiB RAM, WSL2 |
| GPU | GTX 1650 4 GB. **Ollama không dùng được**: `ggml_cuda_init: failed to initialize CUDA: device kernel image is invalid`. Driver Windows 537.58 chỉ hỗ trợ CUDA 12.2, còn Ollama 0.35 đóng gói runtime CUDA 12.8. Ollama vì vậy chạy hoàn toàn trên CPU (`inference compute id=cpu`, `total_vram="0 B"`) |
| LLM | Ollama 0.35.0 cục bộ, `qwen3:1.7b` Q4_K_M. Không có tài liệu nào gửi ra ngoài |
| DB | `ailab_t260040_test` (cô lập; alembic head `f3c4d5e60006`). Playwright dùng `ailab_e2e_test`. Số bản ghi của `ailab` trước và sau giống hệt (819/333/96/1259/108) |
| Stack | uvicorn thật, Celery worker thật (broker `filesystem://` vì máy không có Redis), embedding e5-small thật, retrieval dense mặc định |

## 2. Nguyên nhân timeout

Ollama tự đo các chỉ số dưới đây (`prompt_eval_count/duration`, `eval_count/duration`, `load_duration`):

| Chỉ số | Giá trị đo |
| :--- | :--- |
| Prompt RAG thật (5 nguồn, khoảng 4.9k ký tự) | 1 423–1 516 token |
| Tốc độ prefill khi không có cache | 28–37 token/s (cold: 1 476 token trong 40.2s) |
| Tốc độ sinh | 4–10 token/s, trung vị khoảng 7. Dao động theo nhiệt độ CPU laptop |
| Nạp model khi cold | 6.9–8.8s, cộng khoảng 4.7s nạp embedding cho request RAG đầu tiên |
| Prefill khi đang chạy song song pytest (T260039) | 4.7 token/s |

Một request RAG lạnh tốn khoảng 7s nạp model + 40–47s prefill trước khi có token đầu tiên. Ngoài ra, `httpx` timeout 60s là read timeout, nên với non-stream nó giới hạn **cả** quá trình sinh. Request đầu tiên của baseline vì thế timeout ở 64.9s.

Khi CPU bị chia sẻ (như lúc T260039 chạy test song song), prefill giảm xuống khoảng 5 token/s và mọi prompt đều timeout.

Thời gian sinh không phải nút thắt chính: câu trả lời chỉ khoảng 15–48 token.

## 3. Lỗi trạng thái dùng chung và cách sửa

**Lỗi:**
- `rag_stream.py` gán `llm.model = routed_model` lên provider singleton (`lru_cache`). `agent_orchestrator.py` gán `self.llm_provider.model` theo cùng cách.
- Giữa lúc gán và lúc dựng payload có nhiều `await` (SSE, governor), nên request A có thể sinh bằng model mà request B đã chọn.
- `/rag/ask` không định tuyến gì cả. Nó dùng model mà request stream gần nhất để lại.

**Cách sửa:**
- `OllamaLLMProvider` thành dataclass `frozen` (gán thuộc tính sẽ ném `FrozenInstanceError`). Thêm `with_model()` trả về bản sao gắn với model, chỉ dùng trong một request.
- `app/llm/base.bind_model()` dùng chung cho mọi provider.
- `app/services/rag_routing.route_rag_generation()` được **cả** stream lẫn non-stream gọi với cùng logic phân loại, định tuyến và fallback. `RAGResponse` có thêm trường `model_name` (chỉ bổ sung, không phá API cũ).
- Agent orchestrator bind `run.model_name` ngay lúc sinh, kể cả khi run được resume.

**Timeout và hủy request:**
- Timeout được tách thành: connect 5s; read 120s (giới hạn prefill khi stream); deadline tổng 180s (`asyncio.wait_for` cho non-stream, kiểm tra theo từng dòng cho stream). Mọi trường hợp đều quy về `httpx.ReadTimeout`, tức 503 hoặc `llm_unavailable`.
- Dòng `{"error": ...}` giữa luồng stream giờ được ném lỗi, không còn bị nuốt.
- Đóng generator (client ngắt kết nối) sẽ đóng HTTP stream tới Ollama.

**Test xác định** (`tests/test_llm_request_isolation.py`, 11 test):
- Dùng `asyncio.Barrier` để buộc hai request định tuyến xong rồi mới sinh, với các cặp stream+stream, ask+ask và stream+ask, mỗi request một workspace và một model.
- **Trên code cũ: 4/4 test RAG đỏ.** Ví dụ, ở cặp stream+stream cả hai request đều sinh bằng `model-b`.
- Trên code mới: tất cả xanh, và provider dùng chung giữ nguyên model.

## 4. Chọn cấu hình

So sánh chỉ phần sinh, trên cùng 12 prompt RAG thật (retrieval giữ cố định). Chi tiết ở `backend/datasets/evaluation/reports/t260040_llm_config_comparison.json`.

| Cấu hình | Đúng (9 câu có đáp án) | Trích đúng nguồn | Từ chối đúng (3 câu) | Bịa |
| :--- | :--- | :--- | :--- | :--- |
| qwen3:1.7b, prompt gốc, sampling mặc định | 3/9 (6 câu đúng sự thật nhưng thiếu `[Source N]` nên bị guardrail chặn) | 3 | 3/3 | 0 |
| qwen3:0.6b, prompt gốc | 0/9 (từ chối tất cả) | 0 | 3/3 | 0 |
| qwen3:1.7b, prompt gốc, temperature 0 | 2/9 | 2 | 3/3 | 0 |
| qwen3:1.7b + nhắc trích dẫn v2 (kèm câu từ chối nguyên văn) | 8/9 | 7 | 1/3 | 0 |
| **qwen3:1.7b + nhắc trích dẫn, temperature 0 (chọn)** | **9/9** | **8** | 2/3 (1 câu từ chối bằng tiếng Anh, bị guardrail chặn an toàn) | **0** |

**Cấu hình chọn:** `qwen3:1.7b` chạy cục bộ. `ANSWER_INSTRUCTIONS` được đặt ngay sau câu hỏi (`rag_prompt.py`). Thêm `temperature=0`, `num_ctx=4096`, `num_predict=512`, `keep_alive=30m`, read timeout 120s, deadline tổng 180s.

Model nhỏ hơn nhanh hơn khoảng 2 lần nhưng không dùng được. Không chọn provider từ xa vì không có credential và không được phép gửi tài liệu workspace ra ngoài.

## 5. Kiểm chứng E2E với LLM thật

Báo cáo đầy đủ ở `backend/datasets/evaluation/reports/t260040_real_llm_e2e_report.json`.

**Luồng:** đăng ký → đăng nhập → tạo workspace → upload 2 tài liệu `.md` → ingestion thật (5 chunk, 6.3s) → 12 câu hỏi × (stream + non-stream).

| Chỉ số | Stream | Non-stream |
| :--- | :--- | :--- |
| Lỗi hoặc timeout | 0/12 | 0/12 |
| Retrieval: bằng chứng gold có trong nguồn truy xuất | 9/9 | (giống stream) |
| Trả lời đúng (đủ sự thật gold) | 9/9 | 9/9 |
| Trích dẫn grounded (sự thật nằm trong chunk được trích, không có số không được hỗ trợ) | 8/9 | 8/9 |
| Câu đúng sự thật nhưng trích sai nguồn | 1 (q01: "18 ngày" nằm ở Source 1 nhưng model trích Source 2) | 1 |
| Câu không có đáp án: từ chối chuẩn / bị chặn an toàn / bịa | 1 / 2 / **0** | 1 / 2 / **0** |
| TTFT p50 / max | 8.6s / 27.2s | – |
| Tổng p50 / max | 13.0s / 29.7s | 3.9s / 7.5s* |

\* Request non-stream chạy ngay sau request stream có **cùng prompt**, nên Ollama dùng lại KV cache. Con số non-stream vì thế lạc quan. Con số stream mới phản ánh request đầu tiên của mỗi câu.

**Các kiểm tra khác:**
- **Hội thoại:** câu tiếp nối "Còn vị trí chuyên viên?" trả lời đúng 45 ngày, kèm [Source 1] grounded. Lịch sử được lưu `user, assistant, user, assistant`, và message cuối khớp `message_id` của SSE.
- **Cô lập:**
  - Người ngoài gửi header giả workspace A nhận 403.
  - Người ngoài hỏi trong workspace của mình nhận câu từ chối chuẩn, 0 nguồn của A.
  - Người ngoài đọc tài liệu của A nhận 404.
- **Đồng thời (LLM thật):** chạy song song 2 stream + 1 ask từ 2 tenant. Cả 3 trả lời đúng, mỗi request chỉ thấy tài liệu của workspace mình. Request sau loạt đó vẫn thành công.
- **Timeout thật:** với deadline 3s, `/rag/ask` trả 503 kèm `Retry-After: 5` và thông báo tiếng Việt. API vẫn phục vụ, và request kế tiếp thành công.
- **Cold start** (sau khi unload model): TTFT 51.4s, tổng 58.3s (nạp 6.9s, prefill 1 476 token trong 40.2s ≈ 36.7 token/s, sinh 48 token trong 6.9s ≈ 7 token/s). Với read timeout cũ 60s request này sát ngưỡng; với 120s thì còn dư.

## 6. Kiểm thử tự động

| Bộ | Kết quả |
| :--- | :--- |
| Backend pytest toàn bộ (`ailab_t260040_test`) | **601 passed** (589 trước đó + 11 test isolation + 1 test prompt) |
| Ruff `app tests` | sạch |
| Frontend `npm run build` | thành công |
| Playwright (`ailab_e2e_test`) | **28 passed** |

## 7. Giới hạn còn lại

1. **Độ trễ:** chỉ có CPU. Request đầu tiên hoặc request có ngữ cảnh mới có TTFT khoảng 25–50s, và tới khoảng 58s khi cold. Không phù hợp production. Cần cập nhật driver NVIDIA phía Windows (≥ bản hỗ trợ CUDA 12.8) để Ollama dùng GTX 1650, hoặc dùng máy có GPU.
2. **Đồng thời:** Ollama chạy `OLLAMA_NUM_PARALLEL=1`, nên các request xếp hàng. Governor (mặc định 2) có thể trả 504 sau 15s chờ khi tải lớn. Chưa đo tải trên 3 request.
3. **Chất lượng:** bộ đánh giá chỉ có 12 câu, 2 tài liệu ngắn, 1 lần chạy. Trích sai nguồn dù sự thật đúng (q01) không bị guardrail phát hiện, vì guardrail chỉ kiểm tra cú pháp `[Source N]`. Model đôi khi từ chối bằng tiếng Anh, khiến người dùng thấy "Không thể xác minh…" thay vì câu từ chối chuẩn.
4. **KV cache của Ollama** làm thời gian prefill dao động lớn (28 đến hơn 5 000 token/s tùy prefix trùng). Số liệu p50 phụ thuộc thứ tự câu hỏi.
5. Chưa đo trên tài liệu dài (nhiều hơn 5 chunk khác nhau) hoặc lịch sử hội thoại dài gần giới hạn 4 000 ký tự.
