# T260029 — HỒ SƠ ĐÍNH CHÍNH & CHUẨN HÓA BẰNG CHỨNG HIỆU NĂNG (PHASE D1 EVIDENCE ERRATA & ADDENDUM)

**Mã tài liệu:** `T260029-D1-ERRATA`
**Dự án:** AI Knowledge Lab
**Nhánh Git:** `feature/T260029` (Commit HEAD: `2011408e4cf8cfbe346a94fa6421fda361eb24eb`)
**Ngày lập hồ sơ:** 2026-11-09
**Trạng thái nghiệm thu chính thức:** `T260029_D1 = ACCEPTED_WITH_LIMITATIONS`
**Quy tắc bất biến:** Không sửa đổi raw artifact đo lường; toàn bộ đính chính được công bố công khai dưới dạng hồ sơ bổ sung (Addendum / Errata).

---

## 1. NGUYÊN BẢN BẰNG CHỨNG ĐÃ ĐƯỢC BẢO TỒN (PRESERVED RAW ARTIFACTS)

Toàn bộ các tệp đo lường thô sinh ra từ phiên benchmark được bảo toàn nguyên trạng và đã được chuyển giao vào repository:

| Tên tệp artifact | Vị trí lưu trữ trong Repository | SHA-256 Checksum |
| :--- | :--- | :--- |
| **Benchmark Script** | `backend/scripts/benchmarks/phase_d1_performance_suite.py` | `bf300a1b647361cdfd3f7a0f058afadcff17ca73a4efdfc76fec4314fa25fcc3` *(kèm pre-commit safety guards)* |
| **Raw JSON Results** | `docs/testing/artifacts/phase_d1_performance_results.json` | `23d35c1fbc21091eb18381f6bbe3594ff5752d8ba5158c4b6ad4fc4c917a14ac` |
| **Execution Log** | Phiên thực thi độc lập Task 5659 | `3c5d258b030d5c403b47a1828e9404ff17b79d2e03b8fb7ed058b479eb049a85` |

*Xác nhận an toàn:* Tệp raw JSON và script không chứa thông tin nhạy cảm, credentials thực tế hay JWT tokens. Đã bổ sung hướng dẫn cảnh báo an toàn và yêu cầu database độc lập khi chạy lại benchmark.

---

## 2. BẢNG HIỆU CHỈNH 9 VẤN ĐỀ TỪ INDEPENDENT AUDIT (ERR-01 ĐẾN ERR-09)

| Mã lỗi | Nhận định ban đầu | Kết quả kiểm toán & Đính chính chính thức | Phân loại & Mức độ |
| :---: | :--- | :--- | :---: |
| **ERR-01** | Executive Summary: *"RAM tiêu thụ dưới 5 GB / 11.6 GB"* | **Đính chính:**<br>- Trước benchmark: $\text{MemTotal} - \text{MemAvailable} \approx 4,813\text{ MB}$.<br>- Sau benchmark: $\text{MemTotal} - \text{MemAvailable} \approx 7,861\text{ MB}$.<br>- Chênh lệch: khoảng **3,048 MB**.<br>- *Lưu ý kỹ thuật:* Đây là ước tính áp lực bộ nhớ toàn hệ thống (system-wide memory pressure từ `/proc/meminfo`), không phải process RSS. Không quy toàn bộ mức tăng này cho tiến trình Ollama do thiếu bằng chứng giám sát per-process riêng biệt. | `INCORRECT_CLAIM`<br>Severity: **P1** |
| **ERR-02** | Báo cáo RPS các endpoint (18.93, 11.10, 7.01 req/s) và gọi là Throughput | **Đính chính:**<br>- Đổi tên chỉ số thành: **`Single-Client Paced Request Rate`**.<br>- Kịch bản kiểm thử cố tình đặt khoảng dừng 50 ms (`await asyncio.sleep(0.05)`) giữa các requests tuần tự trên một client đơn luồng.<br>- Chỉ số này **KHÔNG PHẢI** là Server Throughput, Concurrent Capacity hay khả năng chịu tải bền vững của hệ thống. Không suy diễn throughput từ phép nghịch đảo độ trễ. | `INCORRECT_CLAIM`<br>Severity: **P1** |
| **ERR-03** | Ingestion Celery queue wait & worker: *"Nonems"*, kết luận *"nhanh và nhẹ"* | **Đính chính:**<br>- Loại bỏ hoàn toàn chuỗi diễn giải `"Nonems"`.<br>- Ghi nhận chính thức:<br>&nbsp;&nbsp;`Queue waiting time: NOT_MEASURED`<br>&nbsp;&nbsp;`Worker execution time: NOT_MEASURED_SEPARATELY`<br>- *Nguyên nhân:* Hàm `replace_document_content_and_chunks` tại `repositories/document_chunk.py:158` cố ý gán `processing_started_at = None` khi hoàn tất. Biến này không còn tồn tại khi status chuyển sang `ready`.<br>- Phân biệt rõ: Upload HTTP API mất 28–54 ms; vòng đời bất đồng bộ trong database (`updated_at - created_at`) mất 166–205 ms; tổng thời gian quan sát từ client đến khi polling thấy `ready` là 331–559 ms. Không coi DB timestamp delta là worker processing time chính xác. | `INCORRECT_CLAIM`<br>Severity: **P1** |
| **ERR-04** | Non-streaming RAG P50 = 10.84s, *"bảo đảm sinh trích dẫn [Source 1]"* $\rightarrow$ PASS | **Đính chính:**<br>- Ghi nhận đầy đủ cả 3 mẫu kiểm thử ($n=3$):<br>&nbsp;&nbsp;+ 1 câu trả lời thành công có trích dẫn `[Source 1]` (`latency: 10,838.01 ms`, `sources_count: 3`).<br>&nbsp;&nbsp;+ 2 câu trả lời bị Guardrail từ chối, trả về *"Không thể xác minh câu trả lời từ tài liệu được truy xuất"* (`sources_count: 0`, latencies: 34,548.05 ms và 6,798.86 ms).<br>- **Tỷ lệ từ chối quan sát được:** **2/3 (66.7%)**.<br>- Không vội vàng phân loại refusal là bug; nguyên nhân là do không truy xuất được chunk nguồn liên quan (`sources_count = 0`). Không khẳng định nguyên nhân do ngưỡng similarity nếu thiếu log nội bộ của retrieval pipeline. | `INSUFFICIENT_EVIDENCE`<br>Severity: **P1** |
| **ERR-05** | Báo cáo PostgreSQL 16.10 native và pgvector 0.8.0 | **Đính chính:** Cập nhật phiên bản thực tế đã được kiểm chứng trực tiếp qua SQL:<br>- **PostgreSQL:** `16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)`.<br>- **pgvector:** `0.8.5`. | `INCORRECT_CLAIM`<br>Severity: **P2** |
| **ERR-06** | Trình bày P95 cho các mẫu nhỏ ($n=15, n=3$) như một chỉ số độc lập | **Đính chính:**<br>- Với phương pháp nearest-rank percentile (`ceil(0.95 * n) - 1`), tại $n=15$, chỉ số P95 rơi vào index 14, **toán học đồng nhất 100% với giá trị MAX**.<br>- Các benchmark có $n=1, 2, 3$ hoàn toàn không đủ cơ sở thống kê để khẳng định phân phối latency.<br>- Giữ lại số liệu đo thô nhưng ghi rõ P95 $\equiv$ MAX do cỡ mẫu nhỏ, không dùng làm cam kết năng lực hệ thống. | `INCORRECT_CLAIM`<br>Severity: **P2** |
| **ERR-07** | Tuyên bố các chỉ số độ trễ *"đạt chuẩn kỹ thuật"* và *"đạt chuẩn production"* | **Đính chính:**<br>- Trong repository hiện tại **chưa có bất kỳ hợp đồng SLA/SLO nào được phê duyệt** bởi Owner/Architect.<br>- Phân loại chính thức của toàn bộ kết quả đo: **`BASELINE_MEASURED_WITH_LIMITATIONS`**.<br>- Toàn bộ số liệu chỉ có ý nghĩa làm mốc đo lường cơ sở (baseline) phục vụ so sánh tương đối, không phải cam kết chất lượng dịch vụ. | `INCORRECT_CLAIM`<br>Severity: **P2** |
| **ERR-08** | Trace Agent WRITE: `historical_write_approval_traces = []` | **Đính chính:**<br>- Raw JSON giữ nguyên mảng rỗng `[]` (không sửa file đo lường thô).<br>- Nguyên nhân: Script truy vấn `WHERE a.status = 'approved'`, trong khi vòng đời hệ thống cập nhật yêu cầu đã hoàn tất sang `status = 'executed'`.<br>- Truy vấn bổ sung (Read-Only) xác nhận các trace lịch sử có thực trong DB:<br>&nbsp;&nbsp;+ Run `fae6bf8c-...`: Goal *"Tạo một tài liệu mới có tên 'SOP Safety'"*, Duration: 66.76s, Status: `executed`.<br>&nbsp;&nbsp;+ Run `1491216a-...`: Goal *"Call create_workspace_document..."*, Duration: 37.94s, Status: `executed`.<br>&nbsp;&nbsp;+ Run `ce8dc94a-...`: Goal *"Call create_workspace_document..."*, Duration: 28.34s, Status: `executed`. | `INSUFFICIENT_EVIDENCE`<br>Severity: **P2** |
| **ERR-09** | Tuyên bố *"hệ thống không rò rỉ bộ nhớ"* | **Đính chính:**<br>- Loại bỏ hoàn toàn tuyên bố này.<br>- Ghi nhận chính thức: **`No long-duration soak test was performed. Memory leak behavior remains unverified.`**<br>- Phiên benchmark chỉ kéo dài 4.5 phút với ~30 requests, không đủ cơ sở để chứng minh tính ổn định bộ nhớ dài hạn. | `INSUFFICIENT_EVIDENCE`<br>Severity: **P2** |

---

## 3. CÁC HIỆU CHỈNH VÀ LÀM RÕ KỸ THUẬT BỔ SUNG

1. **Phân biệt thời gian suy luận LLM của Agent:**
   Báo cáo cũ ghi nhận *"LLM inference chiếm 99.7% thời gian Agent"*. Cần làm rõ: Đây là **Residual Wall-Clock Duration** (tính bằng tổng thời gian API trừ đi thời gian model routing 4.8ms và step execution 181.5ms). Con số 99.7% này phản ánh thời gian chờ tiến trình Ollama xử lý tuần tự 2 lượt ReAct loop trên CPU kết hợp với độ trễ chuyển giao event-loop nội bộ, không phải timestamp micro-level trích xuất từ bên trong Ollama process.
2. **Bản chất CPU Load Average:**
   Chỉ số Load Average sau test đạt **5.96 / 3.33 / 1.50** trên CPU 6 Cores / 12 Threads (i5-10500H) phản ánh độ dài hàng đợi tác vụ của hệ điều hành (~6 processes đang chạy hoặc chờ I/O), **không đồng nghĩa** với việc CPU đã cạn kiệt hoặc đạt 100% CPU utilization.
3. **Chỉ số Streaming TTFT:**
   Chỉ số TTFT = 493.14 ms được kiểm toán xác nhận đã bắt đúng sự kiện SSE đầu tiên có `event == "token"`. Tuy nhiên, chỉ số này chỉ có **cỡ mẫu duy nhất $n=1$**, chỉ mang tính chất minh chứng khả năng kỹ thuật (capability proof), không đại diện cho phân phối độ trễ diện rộng.
4. **Tính bất biến của dữ liệu lịch sử:**
   Việc số lượng bản ghi tăng chính xác theo lượng test case ($Users: 164 \rightarrow 167$, $Docs: 77 \rightarrow 80$, $Runs: 81 \rightarrow 83$) chứng minh không có bản ghi mới nào bị thất thoát, nhưng phương pháp đếm số dòng (count-only) không chứng minh tính bất biến tuyệt đối của các trường dữ liệu lịch sử. Việc bảo toàn được củng cố bằng việc kịch bản kiểm thử không chứa các lệnh `UPDATE` hay `DELETE` trên bảng nghiệp vụ.
5. **Hiệu năng Vector Search khi mở rộng quy mô:**
   Thời gian tìm kiếm cosine distance 1.89 ms chỉ áp dụng trên tập dữ liệu kiểm chuẩn nhỏ (80 documents, khoảng 200 chunks vector). Khi tập dữ liệu tăng lên hàng triệu vectors, thời gian tìm kiếm sẽ thay đổi đáng kể tùy thuộc vào cấu hình Index pgvector (HNSW hoặc IVFFlat) và dung lượng RAM `shared_buffers`.
6. **Giới hạn phạm vi nhiệm vụ (Scope Boundary):**
   Các giải pháp khuyến nghị kỹ thuật (như bật NVIDIA GPU offloading, chuyển đổi Inference Governor sang Redis distributed locks, tối ưu hóa Frontend streaming) chỉ được ghi nhận dưới dạng **Đề xuất phát triển tương lai (Future Enhancements)**, tuyệt đối không được đưa vào scope của nhiệm vụ T260029.

---

## 4. BẢNG TỔNG HỢP HIỆU NĂNG BASELINE CHÍNH THỨC (FINAL BASELINE RECORD)

| Chỉ số / Endpoint | Cỡ mẫu ($n$) | Min | P50 (Median) | Max (P95 $\equiv$ Max) | Phân loại bằng chứng | Đánh giá chính thức |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **API Health Liveness** | 15 | 1.92 ms | 2.51 ms | 3.89 ms | `VERIFIED_REAL` | Baseline đạt chuẩn tiến trình nội bộ |
| **API Health Readiness** | 15 | 29.36 ms | 39.43 ms | 49.85 ms | `VERIFIED_REAL` | Phản hồi probe đa dịch vụ (DB+Redis+Ollama) |
| **API Auth Login** | 15 | 79.83 ms | 89.51 ms | 141.08 ms | `VERIFIED_REAL` | Chi phối bởi hàm băm Bcrypt CPU-bound |
| **API Workspaces List** | 15 | 6.68 ms | 7.50 ms | 10.16 ms | `VERIFIED_REAL` | Truy vấn cơ sở dữ liệu có Index |
| **API Documents List** | 15 | 7.43 ms | 8.40 ms | 18.35 ms | `VERIFIED_REAL` | Truy vấn danh sách tài liệu workspace |
| **API Models List** | 15 | 8.07 ms | 8.65 ms | 13.71 ms | `VERIFIED_REAL` | Truy vấn danh mục model từ cache |
| **Single-Client Paced Rate (/health)** | 15 | — | — | 18.93 req/s | `VERIFIED_REAL` | Đo với 50ms pacing sleep (Không phải server max throughput) |
| **Ingestion TXT (243 B)** | 1 | — | 331.90 ms | — | `VERIFIED_REAL` | Queue wait: NOT_MEASURED; Worker: NOT_MEASURED_SEPARATELY |
| **Ingestion PDF (752 B)** | 1 | — | 431.64 ms | — | `VERIFIED_REAL` | Queue wait: NOT_MEASURED; Worker: NOT_MEASURED_SEPARATELY |
| **Ingestion DOCX (36.8 KB)** | 1 | — | 559.75 ms | — | `VERIFIED_REAL` | Queue wait: NOT_MEASURED; Worker: NOT_MEASURED_SEPARATELY |
| **Query Embedding (e5-small)** | 3 | 27.66 ms | 29.19 ms | 59.98 ms | `VERIFIED_REAL` | Sinh embedding 384 chiều trên CPU |
| **pgvector Cosine Search (`<=>`)** | 3 | 1.70 ms | 1.89 ms | 23.81 ms | `VERIFIED_REAL` | Truy vấn vector trên tập dữ liệu baseline |
| **Streaming RAG TTFT** | 1 | — | 493.14 ms | — | `VERIFIED_REAL` | Token event đầu tiên được phát đi (Cỡ mẫu $n=1$) |
| **RAG Token Generation Rate** | 1 | — | 11.85 tok/s | — | `VERIFIED_REAL` | Suy luận Ollama `qwen3:1.7b` trên CPU |
| **Non-streaming RAG E2E Latency** | 3 | 6.80 s | 10.84 s | 34.55 s | `VERIFIED_REAL` | 1/3 thành công có citation; 2/3 bị từ chối do thiếu context |
| **Agent Model Routing Overhead** | 2 | 4.76 ms | 4.86 ms | 4.95 ms | `VERIFIED_REAL` | Đọc từ bảng `model_routing_decisions` |
| **Agent Tool Execution (`search_docs`)**| 2 | 88.90 ms | 135.20 ms | 181.50 ms | `VERIFIED_REAL` | Đọc từ bảng `agent_steps` |
| **Agent READ E2E Latency** | 2 | 68.39 s | 76.63 s | 84.88 s | `VERIFIED_REAL` | Chi phối bởi 2 lượt LLM ReAct loop trên CPU |
| **Historical Agent WRITE Traces** | 3 | 28.34 s | 37.94 s | 66.76 s | `DERIVED_FROM_TRACE` | Dữ liệu read-only từ các run có status `executed` |

---

## 5. KẾT LUẬN NGHIỆM THU CUỐI CÙNG (FINAL ACCEPTANCE RECORD)

# `T260029_D1 = ACCEPTED_WITH_LIMITATIONS`

### Tuyên bố miễn trừ và ranh giới chấp nhận:
Hồ sơ nghiệm thu Phase D1 chính thức khẳng định:
1. **KHÔNG** tuyên bố hệ thống đạt `PRODUCTION_READY`.
2. **KHÔNG** tuyên bố hệ thống đạt `PERFORMANCE_SLO_PASS` (do chưa có văn bản SLO phê duyệt).
3. **KHÔNG** tuyên bố hệ thống đạt `LOAD_TEST_PASS` (chưa thực hiện kiểm thử tải đồng thời cao).
4. **KHÔNG** tuyên bố hệ thống đạt `SOAK_TEST_PASS` (hành vi rò rỉ bộ nhớ dài hạn chưa được kiểm chứng).

### Các giới hạn kỹ thuật được bảo lưu và chuyển giao sang Phase D2:
- **Giới hạn 1 (CPU-bound LLM Inference):** Tốc độ sinh token đạt ~11.85 tok/s trên CPU khiến độ trễ RAG và Agent ở mức cao (10s – 85s).
- **Giới hạn 2 (Process-Local Governor):** Bộ điều phối suy luận hoạt động theo tiến trình cục bộ, chưa hỗ trợ đa worker phân tán.
- **Giới hạn 3 (Rate Limiting Backpressure):** Khách hàng cần tự xử lý mã phản hồi HTTP 429 khi đạt ngưỡng trần của Redis sliding window.
- **Giới hạn 4 (RAG Retrieval Context Sensitivity):** Tỷ lệ từ chối 2/3 trong kịch bản kiểm thử nhấn mạnh yêu cầu tài liệu phải được chunking và embedding với độ tương đồng ngữ nghĩa đủ cao để vượt qua bộ lọc ngữ cảnh.

Toàn bộ dữ liệu kiểm chuẩn đã được chuẩn hóa, minh bạch hóa và sẵn sàng làm căn cứ cho việc chuyển giao sang Phase D2 khi có chỉ đạo từ người dùng.
