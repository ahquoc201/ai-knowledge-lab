# T260029 — DEPLOYMENT & OPERATIONS RUNBOOK
**Dự án:** AI Knowledge Lab
**Mã tài liệu:** `T260029-RUNBOOK`
**Nhánh áp dụng:** `feature/T260029`
**Phiên bản hệ thống:** v0.1.0 (Post-T260028)
**Ngày cập nhật:** 2026-11-09

---

## 1. PHÂN ĐỊNH RANH GIỚI MÔI TRƯỜNG (ENVIRONMENT TIERS)

> [!IMPORTANT]
> Cấu hình máy trạm phát triển hiện tại (Laptop Windows + WSL2) **KHÔNG PHẢI** là cấu hình triển khai Production đã được nghiệm thu.

| Tiêu chí | Local Development (Môi trường hiện tại) | Staging Candidate (Môi trường tiền sản xuất) | Production Requirements (Mục tiêu sản xuất) |
| :--- | :--- | :--- | :--- |
| **Hạ tầng OS** | Windows 10/11 + WSL2 Ubuntu 24.04 | Dedicated Linux VM / Containerized OS | Kubernetes / Cloud-native Managed Services |
| **Cơ sở dữ liệu** | PostgreSQL 16.15 native (`storage/pgdata`, socket `/tmp`) | PostgreSQL 16 Managed (RDS / Cloud SQL) | PostgreSQL 16 HA Cluster (Primary-Standby, Auto-Failover) |
| **Vector Extension**| pgvector 0.8.5 | pgvector 0.8.5 | pgvector 0.8.5 + HNSW Index tuned |
| **In-Memory Broker**| Redis 7.4-alpine Docker (Port 16379) | Redis 7.4 Standalone Container | Redis 7.4 Cluster / Redis Sentinel (High Availability) |
| **Task Queue** | Celery Worker (Concurrency=2, Prefork) | Celery Workers (Autoscaling pool) | Celery Autoscaling Pods + Dedicated Dead Letter Queue |
| **LLM Runtime** | Ollama `qwen3:1.7b` (CPU Mode, ~11.85 tok/s) | Ollama / vLLM trên GPU (T4 / A10G) | vLLM / TensorRT-LLM GPU Cluster (Tối thiểu 24GB VRAM) |
| **Embedding Engine**| `multilingual-e5-small` (CPU, local cache) | Dedicated Embedding Microservice | GPU-accelerated / Batch Embedding Service |
| **Rate Limiter** | Redis Sliding Window + In-Memory Fallback | Redis Cluster Sliding Window | Multi-region Distributed Token Bucket + Cloud WAF |
| **Inference Governor**| Process-Local Semaphore (`max_concurrency=2`) | Process-Local Semaphore | Distributed Redis Token Bucket / Queue Manager |
| **Bảo mật & Secrets**| File `.env` cục bộ (gitignore) | HashiCorp Vault / AWS Secrets Manager | Cloud KMS + HashiCorp Vault + Secret Rotation tự động |

---

## 2. YÊU CẦU TIỀN ĐỀ HẠ TẦNG (ENVIRONMENT PRE-REQUISITES)

### A. Hệ điều hành & Công cụ phát triển
- Ubuntu 24.04 LTS chạy trên WSL2.
- Python 3.12.3 và môi trường ảo `.venv` tại thư mục `backend/`.
- Node.js v20.x và npm tại thư mục `frontend/`.
- Docker Engine & Docker Compose (cho Redis container).
- PostgreSQL 16 client binaries (`psql`, `pg_dump`, `pg_restore`).

### B. Cấu hình tệp môi trường (`.env`)
Tạo tệp `.env` tại thư mục gốc từ `.env.example`:
```bash
cp .env.example .env
```
Các tham số bắt buộc cho môi trường phát triển:
```ini
APP_NAME=AI Knowledge Lab
APP_ENV=development
MAX_UPLOAD_SIZE_BYTES=5242880

# Database
POSTGRES_USER=ailab
POSTGRES_PASSWORD=local_only_change_me
POSTGRES_DB=ailab
DB_PORT=15432
DATABASE_URL=postgresql+asyncpg://ailab:local_only_change_me@127.0.0.1:15432/ailab

# Security
JWT_SECRET_KEY=replace_with_secure_random_secret_in_prod
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Model & Ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_TIMEOUT_SECONDS=180.0

# Redis & Celery
REDIS_PORT=16379
CELERY_BROKER_URL=redis://127.0.0.1:16379/0
```

---

## 3. QUY TRÌNH KHỞI ĐỘNG HỆ THỐNG THỐNG NHẤT (STARTUP ORDER)

Để đảm bảo các ràng buộc kết nối và tránh lỗi khởi động dây chuyền, hệ thống **bắt buộc** phải được khởi động theo đúng thứ tự 6 bước sau:

```mermaid
flowchart TD
    S1["1. PostgreSQL (Port 15432)"] --> S2["2. Redis Container (Port 16379)"]
    S2 --> S3["3. Ollama Daemon (Port 11434)"]
    S3 --> S4["4. Celery Worker Daemon"]
    S4 --> S5["5. FastAPI Uvicorn (Port 8000)"]
    S5 --> S6["6. React Frontend Vite (Port 5173)"]
```

### Bước 1: Khởi động PostgreSQL 16 Native
```bash
# Đảm bảo không có lock file cũ
rm -f storage/pgdata/postmaster.pid

# Khởi động PostgreSQL daemon trên cổng 15432
/usr/lib/postgresql/16/bin/postgres \
  -D ./storage/pgdata \
  -p 15432 \
  -k /tmp \
  -c listen_addresses=127.0.0.1 &
```
*Kiểm tra:*
```bash
/usr/lib/postgresql/16/bin/pg_isready -h 127.0.0.1 -p 15432
# Kết quả mong đợi: 127.0.0.1:15432 - accepting connections
```

### Bước 2: Khởi động Redis Docker Container
```bash
docker compose up -d redis
```
*Kiểm tra:*
```bash
docker exec ai-knowledge-lab-redis redis-cli ping
# Kết quả mong đợi: PONG
```

### Bước 3: Kiểm tra & Khởi động Ollama
```bash
# Kiểm tra Ollama daemon đang chạy
curl -s http://127.0.0.1:11434/api/tags
# Đảm bảo model qwen3:1.7b sẵn sàng trong catalog
```

### Bước 4: Khởi động Celery Worker
```bash
# Sử dụng script chuẩn hóa của repository
bash scripts/start-worker.sh
```
*Kiểm tra:*
```bash
cd backend && .venv/bin/celery -A app.core.celery_app inspect ping
# Kết quả mong đợi: {'celery@...': {'ok': 'pong'}}
```

### Bước 5: Khởi động FastAPI Backend
```bash
cd backend
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OLLAMA_TIMEOUT_SECONDS=180.0 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
*Kiểm tra:*
```bash
curl -s http://127.0.0.1:8000/api/v1/health/ready
# Kết quả mong đợi: {"status":"healthy", ...}
```

### Bước 6: Khởi động React Frontend
```bash
cd frontend
npm run dev
# Truy cập giao diện tại http://localhost:5173
```

---

## 4. QUY TRÌNH DỪNG HỆ THỐNG AN TOÀN (SHUTDOWN ORDER)

Dừng hệ thống theo thứ tự ngược lại để đảm bảo không ngắt quãng các task đang xử lý dở dang:

1. **Dừng Frontend:** Nhấn `Ctrl + C` tại terminal Vite dev server.
2. **Dừng Backend:** Nhấn `Ctrl + C` hoặc gửi tín hiệu `SIGTERM` tới tiến trình Uvicorn.
3. **Dừng Celery Worker (Graceful Shutdown):**
   ```bash
   pkill -TERM -f "celery -A app.core.celery_app worker"
   ```
   *(Chờ tối đa 15s để worker hoàn tất task hiện tại).*
4. **Dừng Redis Container:**
   ```bash
   docker compose stop redis
   ```
5. **Dừng PostgreSQL Native:**
   ```bash
   /usr/lib/postgresql/16/bin/pg_ctl -D storage/pgdata -m fast stop
   ```

---

## 5. HEALTH & READINESS PROBES

| Endpoint / Command | Giao thức | Ý nghĩa kỹ thuật | Trạng thái hợp lệ |
| :--- | :---: | :--- | :--- |
| `GET /api/v1/health` | HTTP | Liveness: kiểm tra tiến trình FastAPI phản hồi | `200 {"status":"ok"}` |
| `GET /api/v1/health/ready` | HTTP | Readiness: kiểm tra kết nối DB, Redis, Ollama | `200 {"status":"healthy"}` |
| `GET /api/v1/health/database` | HTTP | Database ping probe (`SELECT 1`) | `200 {"status":"ok"}` |
| `celery inspect ping` | Celery | Xác minh worker lắng nghe broker Redis | `{'ok': 'pong'}` |
| `alembic current` | CLI | Xác minh migration schema đồng nhất với code | `e2b3c4d50005 (head)` |

---

## 6. QUY TRÌNH SAO LƯU VÀ KHÔI PHỤC CƠ SỞ DỮ LIỆU (BACKUP & RESTORE)

### A. Sao lưu an toàn (Logical Backup)
Thực hiện sao lưu logic không làm gián đoạn hệ thống:
```bash
mkdir -p storage/backups
/usr/lib/postgresql/16/bin/pg_dump \
  -h 127.0.0.1 -p 15432 -U ailab -d ailab \
  -F c -b -v \
  -f "storage/backups/ailab_backup_$(date +%Y%m%d_%H%M%S).dump"
```

### B. Giới hạn khôi phục (Restore Boundaries)
> [!CAUTION]
> Tuyệt đối không chạy lệnh khôi phục đè (restore) trực tiếp trên cơ sở dữ liệu `ailab` đang vận hành mà chưa có chỉ đạo từ Owner. Khi cần khôi phục kiểm tra, luôn khôi phục sang một database tạm (`ailab_test_restore`).

---

## 7. XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)

1. **Lỗi `FATAL: lock file "postmaster.pid" already exists`:**
   - *Nguyên nhân:* Server hoặc máy tính tắt đột ngột khiến PID cũ còn sót lại.
   - *Khắc phục:* Kiểm tra xem tiến trình cũ có còn chạy không (`pgrep -f postgres`). Nếu không, xóa lock file: `rm -f storage/pgdata/postmaster.pid` và khởi động lại.
2. **Lỗi `ConnectionRefusedError: [Errno 111] Connecting to 127.0.0.1:16379`:**
   - *Nguyên nhân:* Docker daemon chưa bật hoặc Redis container chưa khởi động.
   - *Khắc phục:* Kiểm tra Docker Desktop và chạy `docker compose up -d redis`.
3. **Lỗi `HTTP 429 Too Many Requests` khi chạy test suite:**
   - *Nguyên nhân:* Bộ giới hạn rate limiter Redis tính lũy yêu cầu vượt quota.
   - *Khắc phục:* Trong môi trường unit test, đặt biến môi trường `RATE_LIMIT_REDIS_URL=""` để kích hoạt in-memory sliding window tự động dọn sạch giữa các tests.
4. **Lỗi `Ollama connection timeout`:**
   - *Nguyên nhân:* Khởi động Ollama trên CPU cần thời gian nạp mô hình vào RAM.
   - *Khắc phục:* Đặt `OLLAMA_TIMEOUT_SECONDS=180.0` trong biến môi trường backend.

---

## 8. CẢNH BÁO QUẢN TRỊ MIGRATION VÀ ALEMBIC AUTOGENERATE

> [!WARNING]
> Khi tạo migration mới trong tương lai bằng lệnh `alembic revision --autogenerate`, lập trình viên **BẮT BUỘC** phải rà soát thủ công toàn bộ file migration được sinh ra trước khi chạy `alembic upgrade head`:
>
> 1. **Cảnh giác xóa nhầm chỉ mục pgvector HNSW:**
>    Alembic autogenerate mặc định không nhận diện được chỉ mục vector tùy biến `USING hnsw`. Do đó, Alembic sẽ tự động sinh lệnh sai: `op.drop_index('ix_document_chunks_embedding_hnsw', table_name='document_chunks')`. Lập trình viên **phải xóa bỏ lệnh drop_index này** khỏi file migration.
> 2. **Rà soát các chỉ mục thứ cấp (Secondary Indexes):**
>    Hiện tại có 7 độ lệch metadata chỉ mục (đặt tên khác nhau hoặc composite index thay thế index đơn cột) giữa SQLAlchemy models và PostgreSQL. Tuyệt đối không để autogenerate tự ý xóa hoặc tạo lại các composite index đang phục vụ hiệu năng trong cơ sở dữ liệu.
> 3. **Phạm vi bảo đảm:** Thiết lập hiện tại chỉ được bảo đảm cho môi trường **Local Development**. Trước khi phát hành Production, bắt buộc phải có một migration chuẩn hóa lại toàn bộ metadata index.
