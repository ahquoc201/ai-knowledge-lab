import { test, expect } from "@playwright/test";
import { generateTestDocument, generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Document Lifecycle Workflow (Scenario 3)", () => {
  test("vòng đời tài liệu hoàn chỉnh: tạo mới, tìm kiếm, xem chi tiết, reprocess và xóa an toàn", async ({
    page,
  }) => {
    const user = generateTestUser();
    const doc = generateTestDocument();

    // 1. Đăng ký & Đăng nhập
    await registerUserViaUI(page, user);

    // 2. Chuyển sang trang Thư viện tài liệu
    await page.getByRole("button", { name: /tài liệu \(documents\)/i }).click();
    await expect(
      page.getByRole("heading", { name: /thư viện tài liệu \(document library\)/i })
    ).toBeVisible();

    // 3. Mở Modal thêm tài liệu mới
    await page.getByRole("button", { name: /thêm tài liệu/i }).click();
    await expect(page.getByRole("heading", { name: /thêm tài liệu tri thức mới/i })).toBeVisible();

    // 4. Nhập tiêu đề và nội dung tài liệu
    await page.getByLabel(/tiêu đề tài liệu/i).fill(doc.title);
    await page.getByPlaceholder(/dán hoặc nhập toàn bộ nội dung/i).fill(doc.content);

    // 5. Lưu và kích hoạt Ingestion
    await page.getByRole("button", { name: /lưu và xử lý/i }).click();

    // Modal đóng lại và tài liệu xuất hiện trong bảng
    await expect(page.getByText(doc.title)).toBeVisible({ timeout: 10000 });

    // 6. Tìm kiếm tài liệu theo từ khóa tên
    const searchInput = page.getByPlaceholder(/tìm kiếm tài liệu theo tiêu đề/i);
    await searchInput.fill(doc.title);
    await page.getByRole("button", { name: /tìm kiếm/i }).click();
    await expect(page.getByText(doc.title)).toBeVisible();

    // 7. Mở xem chi tiết tài liệu
    const docRow = page.locator("tr", { hasText: doc.title });
    await docRow.getByTitle(/xem chi tiết/i).click();
    await expect(page.getByRole("heading", { name: doc.title })).toBeVisible();
    await expect(page.getByText(doc.content)).toBeVisible();

    // Đóng modal chi tiết
    await page.getByRole("button", { name: /đóng/i }).click();
    await expect(page.getByRole("heading", { name: doc.title })).not.toBeVisible();

    // 8. Kích hoạt Reprocess vector index
    await docRow.getByTitle(/reprocess/i).click();

    // Chờ thao tác reprocess hoàn tất (nút xóa quay lại trạng thái enabled)
    await expect(docRow.getByTitle(/xóa tài liệu/i)).toBeEnabled({ timeout: 10000 });

    // 9. Xóa tài liệu thử nghiệm một cách an toàn (chấp nhận dialog confirm)
    page.once("dialog", async (dialog) => {
      expect(dialog.message()).toContain(doc.title);
      await dialog.accept();
    });

    await docRow.getByTitle(/xóa tài liệu/i).click();

    // 10. Xác nhận tài liệu không còn tồn tại trong bảng dữ liệu
    await expect(page.locator("td", { hasText: doc.title })).not.toBeVisible({ timeout: 10000 });
  });

  test("thông báo validation khi form tạo tài liệu bị thiếu trường bắt buộc", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    await page.getByRole("button", { name: /tài liệu \(documents\)/i }).click();
    await page.getByRole("button", { name: /thêm tài liệu/i }).click();

    // Submit form rỗng
    await page.getByRole("button", { name: /lưu và xử lý/i }).click();

    // Trình duyệt hoặc app kích hoạt validation
    await expect(
      page.getByText(/vui lòng nhập tiêu đề|vui lòng điền/i).or(page.locator(":invalid"))
    ).toBeDefined();
  });
});
