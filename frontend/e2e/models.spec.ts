import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("AI Model Evaluation & Adaptive Model Routing Workflows (T260027)", () => {
  test("hiển thị Kho mô hình AI (Model Registry) và các badges năng lực", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Mô hình (Models) tab
    await page.locator("#nav-models").click();

    // 2. Xác nhận Header và Subtitle
    await expect(page.getByRole("heading", { name: /quản lý & điều phối mô hình/i })).toBeVisible();
    await expect(page.getByText(/quản lý kho mô hình cục bộ ollama/i)).toBeVisible();

    // 3. Xác nhận các tabs điều hướng
    await expect(page.getByRole("button", { name: /kho mô hình/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /so sánh năng lực/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /cấu hình & thử nghiệm/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /nhật ký quyết định/i })).toBeVisible();

    // 4. Kiểm tra nút Đồng bộ Ollama
    await expect(page.getByRole("button", { name: /đồng bộ ollama/i })).toBeVisible();
  });

  test("xem bảng đối sánh năng lực mô hình và cảnh báo kích thước mẫu nhỏ", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Mô hình tab
    await page.locator("#nav-models").click();

    // 2. Chuyển sang tab So sánh năng lực
    await page.getByRole("button", { name: /so sánh năng lực/i }).click();

    // 3. Xác nhận các cột trong bảng so sánh
    await expect(page.getByText(/bảng đối sánh hiệu năng & an toàn mô hình/i)).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /mô hình/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /năng lực/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /task success/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /rò rỉ dữ liệu/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /cô lập tenant/i })).toBeVisible();

    // 4. Xác nhận cảnh báo kích thước mẫu nhỏ
    await expect(page.getByText(/lưu ý về kích thước mẫu/i)).toBeVisible();
  });

  test("thử nghiệm trình mô phỏng điều phối (Routing Simulator) và kiểm tra kết quả", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Mô hình tab
    await page.locator("#nav-models").click();

    // 2. Chuyển sang tab Cấu hình & Thử nghiệm
    await page.getByRole("button", { name: /cấu hình & thử nghiệm/i }).click();

    // 3. Xác nhận hiển thị form Chính sách và Trình mô phỏng
    await expect(page.getByText(/chính sách điều phối workspace/i)).toBeVisible();
    await expect(page.getByText(/trình mô phỏng điều phối/i)).toBeVisible();

    // 4. Điền nội dung thử nghiệm vào simulator
    const promptArea = page.getByPlaceholder(/nhập prompt hoặc mục tiêu agent để mô phỏng/i);
    await promptArea.fill("Trích xuất thông tin hợp đồng theo chuẩn JSON schema sau");

    // 5. Bấm nút Chạy thử nghiệm mô phỏng
    await page.getByRole("button", { name: /chạy thử nghiệm mô phỏng/i }).click();

    // 6. Xác nhận kết quả điều phối hiển thị
    await expect(page.getByText(/kết quả phân loại/i)).toBeVisible();
    await expect(page.getByText(/mô hình được chọn/i)).toBeVisible();
    await expect(page.getByText(/lý giải điều phối/i)).toBeVisible();
  });

  test("kiểm tra nhật ký quyết định điều phối (Decisions Audit Trail)", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Mô hình tab
    await page.locator("#nav-models").click();

    // 2. Chuyển sang tab Nhật ký Quyết định
    await page.getByRole("button", { name: /nhật ký quyết định/i }).click();

    // 3. Xác nhận tiêu đề kiểm toán observability
    await expect(page.getByText(/nhật ký quyết định điều phối/i)).toBeVisible();

    // 4. Xác nhận bảng hoặc thông báo trạng thái rỗng
    const emptyNotice = page.getByText(/chưa có bản ghi quyết định điều phối nào/i);
    const tableHeader = page.getByRole("columnheader", { name: /thời gian/i });
    await expect(emptyNotice.or(tableHeader)).toBeVisible();
  });
});
