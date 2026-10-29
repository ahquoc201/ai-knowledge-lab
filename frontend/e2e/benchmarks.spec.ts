import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("AI Agent Evaluation & Benchmarking Workflows (T260026)", () => {
  test("hiển thị Benchmarks Dashboard và form khởi tạo benchmark mới", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Kiểm chuẩn (Benchmarks) tab
    await page.locator("#nav-benchmarks").click();

    // 2. Xác nhận Header và Subtitle
    await expect(page.getByRole("heading", { name: /ai agent evaluation & reliability benchmarking/i })).toBeVisible();
    await expect(page.getByText(/khung kiểm chuẩn chất lượng, độ chính xác tool calling/i)).toBeVisible();

    // 3. Mở Modal Chạy Benchmark Mới
    await page.getByRole("button", { name: /chạy benchmark mới/i }).first().click();
    await expect(page.getByText(/khởi chạy kiểm chuẩn ai \(benchmark run\)/i)).toBeVisible();
    await expect(page.getByText(/simulated \(deterministic\)/i)).toBeVisible();
    await expect(page.getByText(/real model \(ollama\)/i)).toBeVisible();

    // 4. Đóng modal
    await page.getByRole("button", { name: /hủy/i }).click();
    await expect(page.getByText(/khởi chạy kiểm chuẩn ai \(benchmark run\)/i)).not.toBeVisible();
  });

  test("thực thi benchmark mô phỏng, xem KPI cards, phân loại 8 nhóm và trace thực thi", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Kiểm chuẩn tab
    await page.locator("#nav-benchmarks").click();

    // 2. Bấm nút Chạy Benchmark Mới
    await page.getByRole("button", { name: /chạy benchmark mới/i }).first().click();

    // 3. Điền thông tin và chạy
    const nameInput = page.getByPlaceholder(/vd: nightly regression benchmark/i);
    await nameInput.fill("Automated E2E Benchmark Test");

    // Click Bắt đầu Benchmark
    await page.getByRole("button", { name: /bắt đầu benchmark/i }).click();

    // 4. Chờ kết quả hiển thị trên Dashboard (KPI summary cards)
    await expect(page.getByText("Automated E2E Benchmark Test").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/success rate/i)).toBeVisible();
    await expect(page.getByText(/tool accuracy/i)).toBeVisible();
    await expect(page.getByText(/citation f1/i)).toBeVisible();
    await expect(page.getByText(/attack blocked/i)).toBeVisible();
    await expect(page.getByText(/benign overblock/i)).toBeVisible();

    // 5. Xác nhận hiển thị phân loại theo 8 nhóm kiểm chuẩn
    await expect(page.getByText(/phân loại theo 8 nhóm kiểm chuẩn/i)).toBeVisible();

    // 6. Test Case Explorer: lọc trạng thái PASS
    await page.getByRole("button", { name: "PASS" }).click();
    await expect(page.getByText(/test case explorer/i)).toBeVisible();

    // 7. Lọc Adversarial
    await page.getByRole("button", { name: "Adversarial" }).click();
    await expect(page.getByText(/adversarial attack/i).first()).toBeVisible();

    // 8. Bấm nút Trace để xem Sanitized Execution Trace
    const traceBtn = page.getByRole("button", { name: /trace/i }).first();
    await expect(traceBtn).toBeVisible();
    await traceBtn.click();

    // Xác nhận Trace Modal hiển thị
    await expect(page.getByText(/sanitized execution trace:/i)).toBeVisible();
    await expect(page.getByText(/toàn bộ token, mật khẩu và pii đã được loại bỏ/i)).toBeVisible();

    // Đóng Trace modal
    await page.getByRole("button", { name: /đóng/i }).click();
    await expect(page.getByText(/sanitized execution trace:/i)).not.toBeVisible();
  });

  test("so sánh hai lần chạy benchmark phát hiện deltas và không hồi quy", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Kiểm chuẩn tab
    await page.locator("#nav-benchmarks").click();

    // Tạo Run 1 (Baseline)
    await page.getByRole("button", { name: /chạy benchmark mới/i }).first().click();
    await page.getByPlaceholder(/vd: nightly regression benchmark/i).fill("Baseline Run 1");
    await page.getByRole("button", { name: /bắt đầu benchmark/i }).click();
    await expect(page.getByText("Baseline Run 1").first()).toBeVisible({ timeout: 15000 });

    // Tạo Run 2 (Current)
    await page.getByRole("button", { name: /chạy benchmark mới/i }).first().click();
    await page.getByPlaceholder(/vd: nightly regression benchmark/i).fill("Current Run 2");
    await page.getByRole("button", { name: /bắt đầu benchmark/i }).click();
    await expect(page.getByText("Current Run 2").first()).toBeVisible({ timeout: 15000 });

    // 2. Bấm nút So sánh Baseline
    const compareBtn = page.getByRole("button", { name: /so sánh baseline/i });
    await expect(compareBtn).toBeVisible({ timeout: 10000 });
    await expect(compareBtn).toBeEnabled({ timeout: 10000 });
    await compareBtn.click();

    // 3. Xác nhận Comparison Modal mở ra với phân tích deltas
    await expect(page.getByText(/so sánh kiểm chuẩn với baseline/i)).toBeVisible();
    await expect(page.getByText(/tóm tắt phân tích:/i)).toBeVisible();
    await expect(page.getByText(/chỉ số đo lường/i)).toBeVisible();
    await expect(page.getByText(/độ lệch \(delta\)/i)).toBeVisible();

    // Đóng Modal
    await page.getByRole("button", { name: /đóng/i }).click();
    await expect(page.getByText(/so sánh kiểm chuẩn với baseline/i)).not.toBeVisible();
  });
});
