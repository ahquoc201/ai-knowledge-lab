import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Navigation and Layout Workflows (Scenario 4)", () => {
  test("người dùng chưa đăng nhập luôn thấy màn hình xác thực", async ({ page }) => {
    // Truy cập root trực tiếp không có token
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /đăng nhập hệ thống/i })).toBeVisible();
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).not.toBeVisible();
  });

  test("điều hướng liên tục qua tất cả các tab chính mà không phát sinh lỗi", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Documents tab
    await page.getByRole("button", { name: /tài liệu \(documents\)/i }).click();
    await expect(
      page.getByRole("heading", { name: /thư viện tài liệu \(document library\)/i })
    ).toBeVisible();

    // 2. Chuyển sang AI Chat / RAG tab
    await page.getByRole("button", { name: /AI Chat \/ RAG/i }).click();
    await expect(page.getByRole("heading", { name: /AI RAG Assistant/i })).toBeVisible();
    await expect(page.getByText(/Cuộc trò chuyện mới/i)).toBeVisible();

    // 3. Chuyển sang Cấu hình / Settings tab
    await page.getByRole("button", { name: /cấu hình \/ audit/i }).click();
    await expect(page.getByRole("heading", { name: /cấu hình & giám sát hệ thống/i })).toBeVisible();
    await expect(page.getByText(/chính sách phòng vệ dữ liệu/i)).toBeVisible();
    await expect(page.getByRole("main").getByText(user.email)).toBeVisible();

    // 4. Quay lại Dashboard
    await page.getByRole("button", { name: /dashboard/i }).first().click();
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible();
  });
});
