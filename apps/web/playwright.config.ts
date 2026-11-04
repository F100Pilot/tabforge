import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack (API, stub worker, built web app).
 * CI starts the stack in the `e2e` job (.github/workflows/ci.yml). Locally: run the API in env=dev
 * without SMTP and dev_auth, the stub worker and `pnpm start -p 3100`, then
 * `E2E_API_LOG=<api log file> pnpm e2e`.
 */
export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.e2e.ts", // keeps these out of vitest's *.test/*.spec pattern
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_WEB_URL ?? "http://localhost:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
