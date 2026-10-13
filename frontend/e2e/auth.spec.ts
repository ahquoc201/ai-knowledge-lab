import { test, expect } from "@playwright/test";
import { generateTestUser } from "./helpers/test-data";

test.describe("Authentication Workflow (Scenario 1 & 5)", () => {
  test("hiển thị trang đăng nhập và tiêu đề thương hiệu", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/AI Knowledge Lab/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /đăng nhập hệ thống/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/mật khẩu/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /đăng nhập ngay/i })).toBeVisible();
  });

  test("thông báo lỗi khi nhập mật khẩu quá ngắn (< 8 ký tự)", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/email/i).fill("test_short@example.com");
    await page.getByLabel(/mật khẩu/i).fill("short");
    await page.getByRole("button", { name: /đăng nhập ngay/i }).click();

    await expect(page.getByText(/mật khẩu phải có ít nhất 8 ký tự/i)).toBeVisible();
  });

  test("thông báo lỗi khi đăng nhập với sai mật khẩu", async ({ page }) => {
    const user = generateTestUser();
    await page.goto("/");
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill("WrongPassword123!");
    await page.getByRole("button", { name: /đăng nhập ngay/i }).click();

    // Verification: Error alert appears without crashing
    await expect(
      page.getByText(/invalid email or password|không chính xác|không thành công/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test("đăng ký tài khoản mới, tự động đăng nhập vào Dashboard và đăng xuất thành công", async ({
    page,
  }) => {
    const user = generateTestUser();
    await page.goto("/");

    // Chuyển sang form Đăng ký
    await page.getByRole("button", { name: /chưa có tài khoản/i }).click();
    await expect(page.getByRole("heading", { name: /tạo tài khoản mới/i })).toBeVisible();

    // Nhập thông tin tài khoản mới
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill(user.password);
    await page.getByRole("button", { name: /tạo tài khoản/i }).click();

    // Xác nhận vào được Dashboard
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText(user.email)).toBeVisible();

    // Thực hiện Đăng xuất
    await page.getByRole("button", { name: /logout|đăng xuất/i }).click();

    // Xác nhận quay lại trang Auth và không còn truy cập được protected content
    await expect(page.getByRole("heading", { name: /đăng nhập hệ thống/i })).toBeVisible();
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).not.toBeVisible();
  });

  test("thông báo lỗi phù hợp khi đăng ký với email đã tồn tại (HTTP 409)", async ({
    page,
  }) => {
    const user = generateTestUser();
    await page.goto("/");

    // Đăng ký lần 1
    await page.getByRole("button", { name: /chưa có tài khoản/i }).click();
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill(user.password);
    await page.getByRole("button", { name: /tạo tài khoản/i }).click();

    // Chờ vào Dashboard rồi logout
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("button", { name: /logout|đăng xuất/i }).click();

    // Thử đăng ký lại với cùng email
    await page.getByRole("button", { name: /chưa có tài khoản/i }).click();
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill(user.password);
    await page.getByRole("button", { name: /tạo tài khoản/i }).click();

    // Xác nhận thông báo lỗi email đã tồn tại xuất hiện và UI không bị crash
    await expect(
      page.getByText(/email is already registered|đã được đăng ký|đã tồn tại/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test("đăng nhập thành công với tài khoản đã đăng ký", async ({ page }) => {
    const user = generateTestUser();

    // Bước 1: Tạo tài khoản trước
    await page.goto("/");
    await page.getByRole("button", { name: /chưa có tài khoản/i }).click();
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill(user.password);
    await page.getByRole("button", { name: /tạo tài khoản/i }).click();
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
      timeout: 10000,
    });

    // Logout
    await page.getByRole("button", { name: /logout|đăng xuất/i }).click();
    await expect(page.getByRole("heading", { name: /đăng nhập hệ thống/i })).toBeVisible();

    // Bước 2: Đăng nhập lại
    await page.getByLabel(/email/i).fill(user.email);
    await page.getByLabel(/mật khẩu/i).fill(user.password);
    await page.getByRole("button", { name: /đăng nhập ngay/i }).click();

    // Xác nhận vào Dashboard thành công
    await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
      timeout: 10000,
    });
  });
});
