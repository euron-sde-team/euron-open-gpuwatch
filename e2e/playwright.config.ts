import { defineConfig, devices } from "@playwright/test";

/**
 * Browser end-to-end tests against the running local stack (`make up && make demo`): the
 * dashboard, the API and worker, Postgres, Redis, Mailpit, the simulated demo agents and,
 * on Floci, KMS, S3 and SES.
 *
 *   pnpm test                 every suite
 *   E2E_HEADED=1 pnpm test    watch it
 *
 * The suites share one demo database, so they run in a single worker, in file order.
 */
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: process.env.WEB_URL || "http://localhost:4410",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    headless: !process.env.E2E_HEADED,
    storageState: ".auth/owner.json",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
