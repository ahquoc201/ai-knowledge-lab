import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Serial execution to ensure deterministic state and avoid concurrency race conditions
  reporter: [
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["list"],
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: ["--no-sandbox", "--disable-setuid-sandbox"],
          env: {
            LD_LIBRARY_PATH: `/home/anhnq/.cache/ms-playwright/chromium-1248/chrome-linux64:/home/anhnq/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64:${process.env.LD_LIBRARY_PATH || ""}`,
          },
        },
      },
    },
  ],
  webServer: [
    {
      command:
        "cd ../backend && HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DATABASE_URL='postgresql+asyncpg://ailab:local_only_change_me@/ailab?host=/tmp&port=15432' .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
