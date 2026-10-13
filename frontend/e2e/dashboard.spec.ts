import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Dashboard Workflow (Scenario 2)", () => {
  test("hiển thị các khối KPI, trạng thái kết nối backend và các chỉ số dữ liệu thật", async ({
    page,
  }) => {
    // Thu thập các console error để phát hiện JavaScript runtime error nghiêm trọng
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // Xác nhận tiêu đề chính và breadcrumb
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible();
    await expect(page.getByText(/Dashboard Tổng quan/i)).toBeVisible();

    // Xác nhận API Health indicator hiển thị trạng thái kết nối thật
    await expect(page.getByText(/API Online/i)).toBeVisible({ timeout: 10000 });

    // Xác nhận 4 thẻ KPI thống kê
    await expect(page.getByText(/tổng tài liệu/i)).toBeVisible();
    await expect(page.getByText(/sẵn sàng truy xuất/i)).toBeVisible();
    await expect(page.getByText(/đang xử lý/i)).toBeVisible();
    await expect(page.getByText(/lỗi xử lý/i)).toBeVisible();

    // Xác nhận phần Guardrails kiến trúc
    await expect(page.getByText(/strict citation validator/i)).toBeVisible();
    await expect(page.getByText(/pgvector semantic search/i)).toBeVisible();
    await expect(page.getByText(/standardized refusal policy/i)).toBeVisible();

    // Không có console errors nghiêm trọng
    const fatalErrors = consoleErrors.filter(
      (err) =>
        !err.includes("favicon.ico") &&
        !err.includes("Failed to load resource")
    );
    expect(fatalErrors.length).toBe(0);
  });

  test("nút điều hướng nhanh chuyển hướng đến đúng trang tài liệu", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // Nhấp nút "Quản lý tài liệu" trên banner
    await page.getByRole("button", { name: /quản lý tài liệu/i }).click();

    // Xác nhận đã chuyển sang trang Thư viện tài liệu
    await expect(
      page.getByRole("heading", { name: /thư viện tài liệu \(document library\)/i })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /thêm tài liệu/i })).toBeVisible();
  });
});
