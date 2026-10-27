import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Governed AI Agent Runtime Workflows (T260025)", () => {
  test("hiển thị Agent Workspace và form khởi tạo nhiệm vụ mới", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // 1. Chuyển sang Governed Agent tab
    await page.locator("#nav-agent").click();

    // 2. Xác nhận Header trang
    await expect(page.getByRole("heading", { name: /governed ai agent runtime/i })).toBeVisible();

    // 3. Xác nhận Empty State khi chưa có run nào
    await expect(page.getByRole("heading", { name: /chưa chọn agent run/i })).toBeVisible();

    // 4. Bấm nút Tạo Nhiệm Vụ Mới để mở Form
    const createBtn = page.getByRole("button", { name: "Tạo Nhiệm Vụ Mới" }).first();
    await expect(createBtn).toBeVisible();
    await createBtn.click();
    if (!(await page.getByText(/thiết lập governed agent run/i).isVisible())) {
      await page.getByRole("button", { name: "Tạo Nhiệm Vụ Mới" }).last().click();
    }

    // 5. Xác nhận Form thiết lập Agent Run hiển thị với các controls
    await expect(page.getByText(/thiết lập governed agent run/i)).toBeVisible();
    await expect(page.getByPlaceholder(/ví dụ: tìm các tài liệu nói về kiến trúc/i)).toBeVisible();
    await expect(page.getByText(/danh sách công cụ được phép/i)).toBeVisible();
    await expect(page.getByText(/tìm kiếm tài liệu \(search docs\)/i)).toBeVisible();
    await expect(page.getByText(/tạo tài liệu mới \(create document\)/i)).toBeVisible();
  });

  test("thực thi nhiệm vụ đa bước với Policy Enforcement và Human Approval cho WRITE tool", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    const mockRunId = "11111111-2222-3333-4444-555555555555";
    const mockStep1Id = "aaaaaaaa-1111-2222-3333-444444444441";
    const mockStep2Id = "aaaaaaaa-1111-2222-3333-444444444442";
    const mockApprovalId = "bbbbbbbb-1111-2222-3333-444444444444";

    let approvalDecided = false;

    // Intercept agent runs API để giả lập chu trình chạy agent có phê duyệt
    await page.route("**/api/v1/agent/runs*", async (route) => {
      const method = route.request().method();
      if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [
              {
                id: mockRunId,
                workspace_id: "00000000-0000-0000-0000-000000000001",
                goal: "Tổng hợp tài liệu kiến trúc và tạo tài liệu mới",
                status: approvalDecided ? "completed" : "awaiting_approval",
                current_step: approvalDecided ? 2 : 1,
                max_steps: 8,
                tool_call_count: approvalDecided ? 2 : 1,
                sources_count: 1,
                created_at: new Date().toISOString(),
                completed_at: approvalDecided ? new Date().toISOString() : null,
              },
            ],
            total: 1,
            limit: 30,
            offset: 0,
          }),
        });
      } else if (method === "POST") {
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: mockRunId,
            workspace_id: "00000000-0000-0000-0000-000000000001",
            initiated_by: "test-user-id",
            goal: "Tổng hợp tài liệu kiến trúc và tạo tài liệu mới",
            status: "awaiting_approval",
            current_step: 1,
            max_steps: 8,
            max_tool_calls: 10,
            tool_call_count: 1,
            final_answer: null,
            sources: [{ title: "Backend Architecture", document_id: "doc-1" }],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            completed_at: null,
            steps: [
              {
                id: mockStep1Id,
                step_number: 1,
                tool_name: "search_workspace_documents",
                arguments: { query: "kiến trúc backend" },
                status: "succeeded",
                result: { total_found: 1 },
                created_at: new Date().toISOString(),
                completed_at: new Date().toISOString(),
              },
              {
                id: mockStep2Id,
                step_number: 2,
                tool_name: "create_workspace_document",
                arguments: {
                  title: "Tổng hợp Kiến trúc Backend",
                  content: "Tài liệu tóm tắt kiến trúc backend và các module.",
                },
                status: "awaiting_approval",
                result: null,
                created_at: new Date().toISOString(),
                completed_at: null,
              },
            ],
            pending_approval: {
              id: mockApprovalId,
              run_id: mockRunId,
              step_id: mockStep2Id,
              tool_name: "create_workspace_document",
              payload: {
                tool_name: "create_workspace_document",
                required_permission: "document.create",
                impact: "Tạo tài liệu mới trong workspace: Tổng hợp Kiến trúc Backend",
                arguments: {
                  title: "Tổng hợp Kiến trúc Backend",
                  content: "Tài liệu tóm tắt kiến trúc backend và các module.",
                },
              },
              status: "pending",
              expires_at: new Date(Date.now() + 600000).toISOString(),
              created_at: new Date().toISOString(),
              decided_at: null,
              decision_reason: null,
            },
          }),
        });
      }
    });

    await page.route(`**/api/v1/agent/runs/${mockRunId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: mockRunId,
          workspace_id: "00000000-0000-0000-0000-000000000001",
          initiated_by: "test-user-id",
          goal: "Tổng hợp tài liệu kiến trúc và tạo tài liệu mới",
          status: approvalDecided ? "completed" : "awaiting_approval",
          current_step: approvalDecided ? 2 : 1,
          max_steps: 8,
          max_tool_calls: 10,
          tool_call_count: approvalDecided ? 2 : 1,
          final_answer: approvalDecided
            ? "Đã đọc các tài liệu về kiến trúc backend và tạo thành công tài liệu 'Tổng hợp Kiến trúc Backend'."
            : null,
          sources: [{ title: "Backend Architecture", document_id: "doc-1" }],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          completed_at: approvalDecided ? new Date().toISOString() : null,
          steps: [
            {
              id: mockStep1Id,
              step_number: 1,
              tool_name: "search_workspace_documents",
              arguments: { query: "kiến trúc backend" },
              status: "succeeded",
              result: { total_found: 1 },
              created_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
            },
            {
              id: mockStep2Id,
              step_number: 2,
              tool_name: "create_workspace_document",
              arguments: {
                title: "Tổng hợp Kiến trúc Backend",
                content: "Tài liệu tóm tắt kiến trúc backend và các module.",
              },
              status: approvalDecided ? "succeeded" : "awaiting_approval",
              result: approvalDecided ? { document_id: "new-doc-123", status: "created" } : null,
              created_at: new Date().toISOString(),
              completed_at: approvalDecided ? new Date().toISOString() : null,
            },
          ],
          pending_approval: approvalDecided
            ? null
            : {
                id: mockApprovalId,
                run_id: mockRunId,
                step_id: mockStep2Id,
                tool_name: "create_workspace_document",
                payload: {
                  tool_name: "create_workspace_document",
                  required_permission: "document.create",
                  impact: "Tạo tài liệu mới trong workspace: Tổng hợp Kiến trúc Backend",
                  arguments: {
                    title: "Tổng hợp Kiến trúc Backend",
                    content: "Tài liệu tóm tắt kiến trúc backend và các module.",
                  },
                },
                status: "pending",
                expires_at: new Date(Date.now() + 600000).toISOString(),
                created_at: new Date().toISOString(),
                decided_at: null,
                decision_reason: null,
              },
        }),
      });
    });

    await page.route(`**/api/v1/agent/approvals/${mockApprovalId}/approve*`, async (route) => {
      approvalDecided = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: mockRunId,
          workspace_id: "00000000-0000-0000-0000-000000000001",
          initiated_by: "test-user-id",
          goal: "Tổng hợp tài liệu kiến trúc và tạo tài liệu mới",
          status: "completed",
          current_step: 2,
          max_steps: 8,
          max_tool_calls: 10,
          tool_call_count: 2,
          final_answer:
            "Đã đọc các tài liệu về kiến trúc backend và tạo thành công tài liệu mới: 'Tổng hợp Kiến trúc Backend'.",
          sources: [
            {
              document_id: "doc-111",
              title: "Backend Architecture Overview",
              relevance: "Tham chiếu chính về thiết kế hệ thống",
            },
          ],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          steps: [
            {
              id: mockStep1Id,
              step_number: 1,
              tool_name: "search_workspace_documents",
              arguments: { query: "backend architecture" },
              status: "succeeded",
              result: { count: 1 },
              created_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
            },
            {
              id: mockStep2Id,
              step_number: 2,
              tool_name: "create_workspace_document",
              arguments: {
                title: "Tổng hợp Kiến trúc Backend",
                content: "Tài liệu tóm tắt kiến trúc backend và các module.",
              },
              status: "succeeded",
              result: { document_id: "new-doc-123", status: "created" },
              created_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
            },
          ],
          pending_approval: null,
        }),
      });
    });

    // 1. Chuyển sang Governed Agent tab
    await page.locator("#nav-agent").click();

    // 2. Mở form tạo nhiệm vụ
    await page.getByRole("button", { name: "Tạo Nhiệm Vụ Mới" }).first().click();

    // 3. Nhập mục tiêu
    const goalInput = page.getByPlaceholder(/ví dụ: tìm các tài liệu nói về kiến trúc/i);
    await goalInput.fill("Tổng hợp tài liệu kiến trúc và tạo tài liệu mới");

    // 4. Click Kích hoạt Governed Agent
    await page.getByRole("button", { name: /kích hoạt governed agent/i }).click();

    // 5. Xác nhận timeline hiển thị step 1 search_workspace_documents
    await expect(page.getByText(/search_workspace_documents/i)).toBeVisible();

    // 6. Xác nhận Action Card yêu cầu Phê duyệt xuất hiện
    await expect(page.getByText(/yêu cầu phê duyệt hành động ghi/i)).toBeVisible();
    await expect(page.getByText(/create_workspace_document/i).first()).toBeVisible();
    await expect(page.getByText(/Tổng hợp Kiến trúc Backend/i).first()).toBeVisible();

    // 7. Click Phê duyệt & Thực thi
    const approveBtn = page.getByRole("button", { name: /phê duyệt & thực thi/i });
    await expect(approveBtn).toBeVisible();
    await approveBtn.click();

    // 8. Sau khi approve, mock trả về trạng thái COMPLETED kèm Final Answer
    await expect(page.getByText(/kết quả tổng hợp từ agent/i)).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText(/đã đọc các tài liệu về kiến trúc backend và tạo thành công tài liệu/i)
    ).toBeVisible();
  });

  test("từ chối phê duyệt (Rejection) ngăn chặn thực thi WRITE tool", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    const mockRunId = "22222222-3333-4444-5555-666666666666";
    const mockStepId = "aaaaaaaa-2222-3333-4444-555555555555";
    const mockApprovalId = "bbbbbbbb-2222-3333-4444-555555555555";

    // Mock API Agent Runs: khi POST thì trả về run đang dừng ở bước phê duyệt
    await page.route("**/api/v1/agent/runs*", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: mockRunId,
            workspace_id: "00000000-0000-0000-0000-000000000001",
            initiated_by: "test-user-id",
            goal: "Tác vụ kiểm thử từ chối phê duyệt",
            status: "awaiting_approval",
            current_step: 1,
            max_steps: 8,
            max_tool_calls: 10,
            tool_call_count: 1,
            final_answer: null,
            sources: [],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            completed_at: null,
            steps: [
              {
                id: mockStepId,
                step_number: 1,
                tool_name: "create_workspace_document",
                arguments: { title: "Draft", content: "Not allowed" },
                status: "awaiting_approval",
                result: null,
                created_at: new Date().toISOString(),
                completed_at: null,
              },
            ],
            pending_approval: {
              id: mockApprovalId,
              run_id: mockRunId,
              step_id: mockStepId,
              tool_name: "create_workspace_document",
              payload: {
                tool_name: "create_workspace_document",
                required_permission: "document.create",
                impact: "Tạo tài liệu Draft",
                arguments: { title: "Draft", content: "Not allowed" },
              },
              status: "pending",
              expires_at: new Date(Date.now() + 600000).toISOString(),
              created_at: new Date().toISOString(),
              decided_at: null,
              decision_reason: null,
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], total: 0, limit: 30, offset: 0 }),
        });
      }
    });

    // Mock API Rejection
    await page.route(`**/api/v1/agent/approvals/${mockApprovalId}/reject*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: mockRunId,
          workspace_id: "00000000-0000-0000-0000-000000000001",
          initiated_by: "test-user-id",
          goal: "Tác vụ kiểm thử từ chối phê duyệt",
          status: "completed",
          current_step: 1,
          max_steps: 8,
          max_tool_calls: 10,
          tool_call_count: 1,
          final_answer:
            "Yêu cầu tạo tài liệu đã bị từ chối bởi người phê duyệt. Không có dữ liệu nào được ghi.",
          sources: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          steps: [
            {
              id: mockStepId,
              step_number: 1,
              tool_name: "create_workspace_document",
              arguments: { title: "Draft", content: "Not allowed" },
              status: "rejected",
              result: { error: "Rejected by human approver: Nội dung chưa đạt yêu cầu" },
              created_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
            },
          ],
          pending_approval: null,
        }),
      });
    });

    // 1. Chuyển sang Governed Agent tab
    await page.locator("#nav-agent").click();

    // 2. Mở form tạo nhiệm vụ
    await page.getByRole("button", { name: "Tạo Nhiệm Vụ Mới" }).first().click();

    // 3. Nhập mục tiêu
    const goalInput = page.getByPlaceholder(/ví dụ: tìm các tài liệu nói về kiến trúc/i);
    await goalInput.fill("Tác vụ kiểm thử từ chối phê duyệt");

    // 4. Click Kích hoạt Governed Agent
    await page.getByRole("button", { name: /kích hoạt governed agent/i }).click();

    // 5. Xác nhận Action Card yêu cầu phê duyệt xuất hiện
    await expect(page.getByText(/yêu cầu phê duyệt hành động ghi/i)).toBeVisible();

    // 6. Nhập lý do từ chối
    const reasonInput = page.getByPlaceholder(/ghi chú xác thực kiểm duyệt/i);
    await reasonInput.fill("Nội dung chưa đạt yêu cầu");

    // 7. Click Từ chối
    const rejectBtn = page.getByRole("button", { name: "Từ chối", exact: true });
    await rejectBtn.click();

    // 8. Xác nhận thông báo hoàn tất không ghi dữ liệu
    await expect(
      page.getByText(/yêu cầu tạo tài liệu đã bị từ chối bởi người phê duyệt/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test("người dùng với vai trò VIEWER bị cảnh báo giới hạn quyền và không thể phê duyệt", async ({ page }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    const mockRunId = "33333333-4444-5555-6666-777777777777";
    const mockStepId = "aaaaaaaa-3333-4444-5555-666666666666";
    const mockApprovalId = "bbbbbbbb-3333-4444-5555-666666666666";

    // Mock workspaces list để giả lập vai trò viewer cho workspace này
    await page.route("**/api/v1/workspaces*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "viewer-workspace-id",
            name: "ReadOnly Research Hub",
            role: "viewer",
            is_personal: false,
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    await page.route("**/api/v1/agent/runs*", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: mockRunId,
            workspace_id: "viewer-workspace-id",
            initiated_by: "test-viewer-id",
            goal: "Tác vụ chạy bởi người dùng Viewer",
            status: "awaiting_approval",
            current_step: 1,
            max_steps: 8,
            max_tool_calls: 10,
            tool_call_count: 1,
            final_answer: null,
            sources: [],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            completed_at: null,
            steps: [
              {
                id: mockStepId,
                step_number: 1,
                tool_name: "create_workspace_document",
                arguments: { title: "Viewer Document" },
                status: "awaiting_approval",
                result: null,
                created_at: new Date().toISOString(),
                completed_at: null,
              },
            ],
            pending_approval: {
              id: mockApprovalId,
              run_id: mockRunId,
              step_id: mockStepId,
              tool_name: "create_workspace_document",
              payload: {
                tool_name: "create_workspace_document",
                required_permission: "document.create",
                impact: "Tạo tài liệu mới trong workspace",
                arguments: { title: "Viewer Document" },
              },
              status: "pending",
              expires_at: new Date(Date.now() + 600000).toISOString(),
              created_at: new Date().toISOString(),
              decided_at: null,
              decision_reason: null,
            },
          }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], total: 0, limit: 30, offset: 0 }),
        });
      }
    });

    // Cập nhật localStorage để chọn viewer-workspace-id khi reload
    await page.evaluate(() => {
      localStorage.setItem("current_workspace_id", "viewer-workspace-id");
    });

    // Reload lại trang để WorkspaceContext nhận mock role viewer
    await page.reload();

    // 1. Chuyển sang Governed Agent tab
    await page.locator("#nav-agent").click();

    // 2. Mở form tạo nhiệm vụ
    await page.getByRole("button", { name: "Tạo Nhiệm Vụ Mới" }).first().click();

    // 3. Nhập mục tiêu
    const goalInput = page.getByPlaceholder(/ví dụ: tìm các tài liệu nói về kiến trúc/i);
    await goalInput.fill("Tác vụ chạy bởi người dùng Viewer");

    // 4. Click Kích hoạt Governed Agent
    await page.getByRole("button", { name: /kích hoạt governed agent/i }).click();

    // 5. Xác nhận Action Card có ghi chú cảnh báo vai trò Viewer
    await expect(
      page.getByText(/tài khoản viewer không có quyền thực thi write tool/i)
    ).toBeVisible();

    // 6. Xác nhận nút Phê duyệt bị disabled đối với Viewer
    const approveBtn = page.getByRole("button", { name: /phê duyệt & thực thi/i });
    await expect(approveBtn).toBeDisabled();
  });
});
