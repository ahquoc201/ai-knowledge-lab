import { Page, expect } from "@playwright/test";

export interface TestUser {
  email: string;
  password: string;
}

export interface TestDocument {
  title: string;
  content: string;
}

export function generateTestUser(): TestUser {
  const timestamp = Date.now();
  const randomSuffix = Math.floor(Math.random() * 10000);
  return {
    email: `e2e_user_${timestamp}_${randomSuffix}@example.com`,
    password: "Password123!",
  };
}

export function generateTestDocument(): TestDocument {
  const timestamp = Date.now();
  const randomSuffix = Math.floor(Math.random() * 10000);
  return {
    title: `E2E Document ${timestamp}_${randomSuffix}`,
    content:
      "PostgreSQL supports ACID transactions and SQL queries. The pgvector extension enables vector similarity search for Retrieval-Augmented Generation systems.",
  };
}

export async function registerUserViaUI(page: Page, user: TestUser): Promise<void> {
  await page.goto("/");
  // Switch to register tab if on login
  const registerToggle = page.getByRole("button", {
    name: /chưa có tài khoản|đăng ký/i,
  });
  if (await registerToggle.isVisible()) {
    await registerToggle.click();
  }

  await page.getByLabel(/email/i).fill(user.email);
  await page.getByLabel(/mật khẩu/i).fill(user.password);
  await page.getByRole("button", { name: /tạo tài khoản/i }).click();

  // Verification: should arrive at dashboard
  await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
    timeout: 10000,
  });
}

export async function loginUserViaUI(page: Page, user: TestUser): Promise<void> {
  await page.goto("/");
  // Switch to login tab if on register
  const loginToggle = page.getByRole("button", {
    name: /đã có tài khoản|đăng nhập/i,
  });
  if (await loginToggle.isVisible()) {
    await loginToggle.click();
  }

  await page.getByLabel(/email/i).fill(user.email);
  await page.getByLabel(/mật khẩu/i).fill(user.password);
  await page.getByRole("button", { name: /đăng nhập ngay/i }).click();

  // Verification: should arrive at dashboard
  await expect(page.getByText(/trung tâm điều khiển tri thức/i)).toBeVisible({
    timeout: 10000,
  });
}
