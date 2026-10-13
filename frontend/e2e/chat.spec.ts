import { test, expect } from "@playwright/test";
import { generateTestUser, registerUserViaUI } from "./helpers/test-data";

test.describe("Evidence-Driven AI Chat Workflows (T260022)", () => {
  test("hiển thị đầy đủ không gian làm việc Chat Workspace và Empty State ban đầu", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // Điều hướng đến tab AI Chat
    await page.getByRole("button", { name: /AI Chat \/ RAG/i }).click();

    // Xác nhận header và thanh công cụ
    await expect(page.getByRole("heading", { name: /AI RAG Assistant/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /cuộc trò chuyện mới/i })).toBeVisible();

    // Xác nhận Empty State
    await expect(
      page.getByRole("heading", { name: /trợ lý tri thức AI \(evidence-driven\)/i })
    ).toBeVisible();
    await expect(page.getByText(/bảo chứng nguồn gốc/i)).toBeVisible();
    await expect(page.getByText(/gợi ý câu hỏi bắt đầu/i)).toBeVisible();

    // Xác nhận Chat Composer input
    const composer = page.getByPlaceholder(/đặt câu hỏi về tài liệu của bạn/i);
    await expect(composer).toBeVisible();
  });

  test("hỏi đáp qua streaming SSE, hiển thị inline citation và mở Evidence Panel chi tiết", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    // Điều hướng sang tab Chat
    await page.getByRole("button", { name: /AI Chat \/ RAG/i }).click();

    const mockDocId = "11111111-1111-1111-1111-111111111111";
    const mockChunkId = "22222222-2222-2222-2222-222222222222";
    const mockConvId = "33333333-3333-3333-3333-333333333333";

    // Intercept POST /api/v1/rag/ask/stream để giả lập stream SSE hoàn chỉnh
    await page.route("**/api/v1/rag/ask/stream", async (route) => {
      const sseBody = [
        `event: retrieval_started\ndata: ${JSON.stringify({
          event: "retrieval_started",
          query: "PostgreSQL ACID?",
          conversation_id: mockConvId,
        })}\n\n`,
        `event: retrieval_completed\ndata: ${JSON.stringify({
          event: "retrieval_completed",
          sources: [
            {
              source_index: 1,
              document_id: mockDocId,
              chunk_id: mockChunkId,
              chunk_index: 0,
              content:
                "PostgreSQL tuân thủ các nguyên lý ACID chặt chẽ với cơ chế Multi-Version Concurrency Control (MVCC).",
              similarity: 0.96,
              document_title: "Kiến trúc CSDL PostgreSQL",
              char_start: 0,
              char_end: 105,
            },
          ],
        })}\n\n`,
        `event: generation_started\ndata: ${JSON.stringify({
          event: "generation_started",
        })}\n\n`,
        `event: token\ndata: ${JSON.stringify({
          event: "token",
          token: "PostgreSQL tuân thủ các thuộc tính ACID nhờ cơ chế MVCC ",
        })}\n\n`,
        `event: token\ndata: ${JSON.stringify({
          event: "token",
          token: "[Source 1].",
        })}\n\n`,
        `event: answer_completed\ndata: ${JSON.stringify({
          event: "answer_completed",
          conversation_id: mockConvId,
          message_id: "44444444-4444-4444-4444-444444444444",
          answer:
            "PostgreSQL tuân thủ các thuộc tính ACID nhờ cơ chế MVCC [Source 1].",
          sources: [
            {
              source_index: 1,
              document_id: mockDocId,
              chunk_id: mockChunkId,
              chunk_index: 0,
              content:
                "PostgreSQL tuân thủ các nguyên lý ACID chặt chẽ với cơ chế Multi-Version Concurrency Control (MVCC).",
              similarity: 0.96,
              document_title: "Kiến trúc CSDL PostgreSQL",
              char_start: 0,
              char_end: 105,
            },
          ],
        })}\n\n`,
      ].join("");

      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "X-Conversation-Id": mockConvId,
        },
        body: sseBody,
      });
    });

    // Nhập câu hỏi vào composer và gửi
    const composer = page.getByPlaceholder(/đặt câu hỏi về tài liệu của bạn/i);
    await composer.fill("PostgreSQL ACID?");
    await page.keyboard.press("Enter");

    // 1. Xác nhận tin nhắn User hiển thị
    await expect(page.getByText("PostgreSQL ACID?")).toBeVisible();

    // 2. Xác nhận câu trả lời Assistant hiển thị đầy đủ
    await expect(
      page.getByText(/PostgreSQL tuân thủ các thuộc tính ACID nhờ cơ chế MVCC/i)
    ).toBeVisible();

    // 3. Xác nhận interactive citation button [Source 1]
    const citationBtn = page.getByRole("button", { name: /Source 1/i }).first();
    await expect(citationBtn).toBeVisible();

    // 4. Click citation button để mở Evidence Panel
    await citationBtn.click();

    // 5. Xác nhận Evidence Panel mở ra với đầy đủ thông tin bằng chứng
    const evidenceAside = page.getByLabel(/khung bằng chứng trích dẫn/i);
    await expect(evidenceAside).toBeVisible();
    await expect(evidenceAside.getByText(/bằng chứng \[source 1\]/i)).toBeVisible();
    await expect(evidenceAside.getByText(/kiến trúc CSDL PostgreSQL/i)).toBeVisible();
    await expect(evidenceAside.getByText(/độ khớp: 96%/i)).toBeVisible();
    await expect(
      evidenceAside.getByText(/PostgreSQL tuân thủ các nguyên lý ACID chặt chẽ/i)
    ).toBeVisible();

    // 6. Đóng Evidence Panel
    await page.getByRole("button", { name: /đóng bảng bằng chứng/i }).click();
    await expect(evidenceAside).not.toBeVisible();
  });

  test("quản lý phiên chat: tạo mới cuộc trò chuyện và reset không gian làm việc", async ({
    page,
  }) => {
    const user = generateTestUser();
    await registerUserViaUI(page, user);

    await page.getByRole("button", { name: /AI Chat \/ RAG/i }).click();

    // Mock ask/stream đơn giản
    await page.route("**/api/v1/rag/ask/stream", async (route) => {
      const sseBody = [
        `event: retrieval_completed\ndata: ${JSON.stringify({
          event: "retrieval_completed",
          sources: [],
        })}\n\n`,
        `event: answer_completed\ndata: ${JSON.stringify({
          event: "answer_completed",
          answer: "Không đủ thông tin trong tài liệu để trả lời câu hỏi này.",
          sources: [],
        })}\n\n`,
      ].join("");

      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: sseBody,
      });
    });

    const composer = page.getByPlaceholder(/đặt câu hỏi về tài liệu của bạn/i);
    await composer.fill("Câu hỏi kiểm tra phiên chat");
    await page.keyboard.press("Enter");

    // Tin nhắn xuất hiện
    await expect(page.getByText("Câu hỏi kiểm tra phiên chat")).toBeVisible();

    // Click nút "+ Cuộc trò chuyện mới"
    await page.getByRole("button", { name: /cuộc trò chuyện mới/i }).click();

    // Tin nhắn cũ được xoá khỏi view hiện tại, empty state quay trở lại
    await expect(
      page.getByRole("heading", { name: /trợ lý tri thức AI \(evidence-driven\)/i })
    ).toBeVisible();
  });
});
