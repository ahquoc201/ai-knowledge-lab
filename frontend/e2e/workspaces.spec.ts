import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Secure Workspaces & RBAC Management (T260024)", () => {
  test("người dùng có thể tạo workspace mới, chuyển đổi qua lại và xem thông tin phân quyền", async ({
    page,
  }) => {
    const user = generateTestUser();
    const newWorkspaceName = `Research Lab ${Date.now()}`;

    // 1. Đăng ký & Đăng nhập
    await registerUserViaUI(page, user);

    // 2. Xác thực Workspace cá nhân mặc định trong Switcher
    const switcherBtn = page.locator("#workspace-switcher-button");
    await expect(switcherBtn).toBeVisible({ timeout: 10000 });
    await expect(switcherBtn).toContainText("Personal");

    // 3. Mở dropdown Switcher và chọn Tạo Workspace mới
    await switcherBtn.click();
    await page.getByRole("button", { name: /tạo workspace mới/i }).click();

    // Modal tạo workspace xuất hiện
    await expect(page.getByRole("heading", { name: /tạo workspace mới/i })).toBeVisible();

    // 4. Nhập thông tin Workspace
    await page.getByPlaceholder(/phòng nghiên cứu ai/i).fill(newWorkspaceName);
    await page.getByPlaceholder(/mô tả mục đích/i).fill("Không gian nghiên cứu dữ liệu chuyên biệt");
    await page.getByRole("button", { name: "Tạo Workspace" }).click();

    // 5. Kiểm tra Header tự động switch sang Workspace mới
    await expect(switcherBtn).toContainText(newWorkspaceName, { timeout: 10000 });
    await expect(switcherBtn).toContainText("owner");

    // 6. Điều hướng đến trang Cấu hình / Audit
    await page.getByRole("button", { name: /cấu hình \/ audit/i }).click();
    await expect(page.getByRole("heading", { name: /cấu hình & quản trị workspace/i })).toBeVisible();

    // 7. Chuyển sang Tab Thành viên & Phân quyền
    await page.getByRole("button", { name: /thành viên & phân quyền/i }).click();
    await expect(page.getByRole("table").getByText(user.email)).toBeVisible();
    await expect(page.getByRole("table").getByText(/owner/i)).toBeVisible();

    // 8. Chuyển sang Tab Security Audit Trail
    await page.getByRole("button", { name: /security audit trail/i }).click();
    await expect(page.getByRole("heading", { name: /security audit trail/i })).toBeVisible();
  });
});
