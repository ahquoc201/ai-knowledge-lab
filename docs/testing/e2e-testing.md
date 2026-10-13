# E2E Testing Guide — AI Knowledge Lab

Tài liệu hướng dẫn triển khai, vận hành và duy trì hệ thống kiểm thử tự động End-to-End (E2E) cho nền tảng **AI Knowledge Lab** sử dụng Playwright.

---

## 1. Mục tiêu kiểm thử End-to-End

Hệ thống E2E testing được xây dựng nhằm đảm bảo:
1. **Kiểm chứng trải nghiệm người dùng thực tế (Real User Journeys):** Đảm bảo các luồng công việc cốt lõi (Authentication, Dashboard Monitoring, Document Lifecycle, Navigation) hoạt động chính xác từ giao diện người dùng đến tầng cơ sở dữ liệu PostgreSQL.
2. **Ngăn chặn hồi quy (Zero-Regression):** Tự động phát hiện lỗi khi có thay đổi logic tại frontend, contract API, hoặc database schema.
3. **Độ tin cậy cao (Determinism & Anti-Flakiness):** Sử dụng các web-first assertions (`expect(locator).toBeVisible()`), locators theo chuẩn Accessibility (`getByRole`, `getByLabel`), và bộ dữ liệu thử nghiệm độc lập (`unique timestamped test fixtures`).

---

## 2. Công nghệ sử dụng

| Thành phần | Công nghệ / Thư viện | Phiên bản | Ghi chú |
| :--- | :--- | :--- | :--- |
| **E2E Framework** | `@playwright/test` | ^1.64.0 | Quản lý test suite, assertions, fixtures |
| **Browser Engine** | Chromium (Desktop Chrome) | 156.0.8078.4 | Headless execution |
| **Node.js** | Node.js v24 (NVM) / v18+ | 24.21.0 | Runtime môi trường frontend |
| **Reporting** | Playwright HTML Reporter, List Reporter | Built-in | Báo cáo chi tiết kèm Screenshots, Videos và Traces |

---

## 3. Cấu trúc thư mục kiểm thử

```text
frontend/
├── playwright.config.ts        # Cấu hình Playwright (timeouts, retries, reporting, webServer)
├── e2e/
│   ├── helpers/
│   │   └── test-data.ts        # Dynamic test user/doc generators & UI auth helpers
│   ├── auth.spec.ts            # Scenario 1 & 5: Đăng ký, Đăng nhập, Đăng xuất, Validation, Duplicate 409
│   ├── dashboard.spec.ts       # Scenario 2: Hiển thị KPI, API Health live status, Guardrails
│   ├── documents.spec.ts       # Scenario 3: Tạo mới, Tìm kiếm, Xem chi tiết, Reprocess, Xóa an toàn
│   └── navigation.spec.ts      # Scenario 4: Chuyển tab Sidebar, unauthenticated routing guards
├── playwright-report/          # Báo cáo HTML tự động sinh (được gitignore)
└── test-results/               # Video, screenshots, traces khi test thất bại (được gitignore)
```

---

## 4. Yêu cầu môi trường (Environment Requirements)

Để chạy trọn vẹn bộ test E2E với backend thật:
1. **PostgreSQL 17 + pgvector**: Đang hoạt động trên cổng `15432` (hoặc cổng cấu hình trong `.env`).
2. **Backend FastAPI**: Đang chạy tại `http://127.0.0.1:8000`.
   - Lệnh khởi động backend:
     ```bash
     cd backend
     .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
     ```
3. **Frontend Vite Dev Server**: Đang chạy tại `http://127.0.0.1:5173`.
   - Playwright được cấu hình sẵn `webServer` để tự động tái sử dụng server đang chạy hoặc khởi động `npm run dev` nếu chưa có.

---

## 5. Hướng dẫn cài đặt & Thực thi

### 5.1. Cài đặt ban đầu

Di chuyển vào thư mục `frontend`:
```bash
cd frontend
npm install
npx playwright install chromium
```

> **Lưu ý trên môi trường Linux / WSL2:**
> Nếu thiếu các thư viện chia sẻ của Chromium (`libnspr4.so`, `libnss3.so`, `libasound.so.2`), tải bổ sung dependencies hoặc cấu hình `LD_LIBRARY_PATH` trỏ tới thư mục chứa thư viện:
> ```bash
> export LD_LIBRARY_PATH="/home/anhnq/.cache/ms-playwright/chromium-1248/chrome-linux64:/home/anhnq/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64:$LD_LIBRARY_PATH"
> ```

### 5.2. Các lệnh chạy test

- **Chạy toàn bộ bộ test E2E (Headless mode):**
  ```bash
  npm run test:e2e
  ```

- **Chạy giao diện trực quan Playwright UI Runner:**
  ```bash
  npm run test:e2e:ui
  ```

- **Chạy một file test cụ thể:**
  ```bash
  npx playwright test e2e/auth.spec.ts
  ```

- **Mở báo cáo HTML (Interactive Report):**
  ```bash
  npm run test:e2e:report
  ```

---

## 6. Phạm vi kiểm thử chi tiết (Test Coverage)

### Scenario 1: Authentication & Error Handling (`e2e/auth.spec.ts`)
- `hiển thị trang đăng nhập và tiêu đề thương hiệu`: Xác thực các nhãn, trường nhập liệu và nút đăng nhập.
- `thông báo lỗi khi nhập mật khẩu quá ngắn (< 8 ký tự)`: Kiểm tra validation phía client.
- `thông báo lỗi khi đăng nhập với sai mật khẩu`: Kiểm tra phản hồi HTTP 401 và thông báo lỗi.
- `đăng ký tài khoản mới, tự động đăng nhập vào Dashboard và đăng xuất`: Xác nhận luồng onboard thành công.
- `thông báo lỗi phù hợp khi đăng ký với email đã tồn tại (HTTP 409)`: Xác nhận bảo vệ duplicate registration và xử lý exception an toàn.
- `đăng nhập thành công với tài khoản đã đăng ký`: Xác nhận luồng returning user.

### Scenario 2: Dashboard Metrics & Health Monitoring (`e2e/dashboard.spec.ts`)
- `hiển thị các khối KPI, trạng thái kết nối backend và các chỉ số dữ liệu thật`: Kiểm tra các thẻ KPI (Tổng tài liệu, Sẵn sàng, Đang xử lý, Lỗi), kiểm tra badge `API Online`, bảo đảm không có console runtime error.
- `nút điều hướng nhanh chuyển hướng đến đúng trang tài liệu`: Xác nhận điều hướng trực tiếp từ banner.

### Scenario 3: Document Lifecycle (`e2e/documents.spec.ts`)
- `vòng đời tài liệu hoàn chỉnh`:
  1. Tạo tài liệu kiểm thử với tiêu đề độc lập.
  2. Xác nhận tài liệu xuất hiện trong danh sách.
  3. Tìm kiếm theo tên tài liệu qua ô search filter.
  4. Mở modal xem chi tiết nội dung văn bản.
  5. Kích hoạt thao tác reprocess vector index.
  6. Xóa tài liệu an toàn (xử lý native confirmation dialog `window.confirm`).
  7. Xác nhận tài liệu không còn tồn tại trong bảng dữ liệu.
- `thông báo validation khi form tạo tài liệu bị thiếu trường bắt buộc`: Kiểm tra form validation.

### Scenario 4: Navigation & Protected Routing (`e2e/navigation.spec.ts`)
- `người dùng chưa đăng nhập luôn thấy màn hình xác thực`: Bảo vệ protected workspace view khi không có token.
- `điều hướng liên tục qua tất cả các tab chính`: Chuyển đổi qua lại giữa Dashboard, Thư viện tài liệu, AI Chat Placeholder (T260022), và Cấu hình hệ thống (Settings).

---

## 7. Xem Báo cáo, Screenshots và Traces

Khi có bất kỳ test nào thất bại hoặc khi chạy chế độ retry:
1. **Screenshots:** Tự động chụp lại màn hình tại thời điểm phát sinh lỗi, lưu vào thư mục `frontend/test-results/`.
2. **Trace Recording:** Lưu lại toàn bộ dòng sự kiện DOM, mạng (Network requests), và console logs vào file `trace.zip`.
3. **Mở Playwright Trace Viewer:**
   ```bash
   npx playwright show-trace test-results/<test-folder>/trace.zip
   ```
4. **HTML Report:** Cung cấp biểu đồ trực quan, thời lượng chạy của từng bước, và cho phép lọc theo trạng thái passed/failed:
   ```bash
   npm run test:e2e:report
   ```

---

## 8. Hướng dẫn tích hợp CI/CD (GitHub Actions)

Mẫu cấu hình tham khảo cho pipeline CI:

```yaml
name: Frontend E2E Tests

on:
  push:
    branches: [main, feature/*]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps chromium

      - name: Run E2E Tests
        run: |
          cd frontend
          npm run test:e2e
        env:
          CI: true
          PLAYWRIGHT_BASE_URL: http://127.0.0.1:5173

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7
```

---

## 9. Sự cố đã phát hiện và xử lý (Resolved Issues)

1. **Khắc phục lỗi HTTP 500 tiềm ẩn khi Đăng ký trùng lặp (Concurrency IntegrityError):**
   - *Nguyên nhân:* Trước đây, nếu hai yêu cầu đăng ký cùng email diễn ra đồng thời, `create_user` gây ra `IntegrityError` trên database mà không có session rollback, dẫn đến unhandled 500.
   - *Giải pháp:* Đã bổ sung `try/except IntegrityError` thực hiện `session.rollback()` trong `backend/app/repositories/user.py` và ánh xạ thành `EmailAlreadyRegisteredError` trả về HTTP 409 Conflict chuẩn mực trong `backend/app/services/auth.py`.
2. **Loại bỏ hiện tượng nhấp nháy / Unmount bảng khi tải ngầm (Silent Refresh):**
   - *Nguyên nhân:* Khi chạy `reprocess` hoặc tạo mới tài liệu, `fetchDocuments()` kích hoạt `isLoading = true`, làm unmount toàn bộ table DOM và gây race condition cho các thao tác tiếp theo.
   - *Giải pháp:* Bổ sung cờ `silent = true` cho `fetchDocuments()` khi làm mới sau các thao tác ngầm, giữ nguyên trạng thái bảng và cập nhật dữ liệu mượt mà.
3. **Định danh chính xác Heading & Text Scoping:**
   - *Giải pháp:* Điều chỉnh các selector Playwright sử dụng regex chính xác (`/thư viện tài liệu \(document library\)/i`) và scope email người dùng trong `getByRole("main")` để tránh lỗi đa phần tử (strict mode violation).
