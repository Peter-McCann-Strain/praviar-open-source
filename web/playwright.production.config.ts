import { defineConfig, devices } from "@playwright/test";

const baseUrlValue = process.env.PLAYWRIGHT_PRODUCTION_BASE_URL;

if (!baseUrlValue) {
  throw new Error(
    "PLAYWRIGHT_PRODUCTION_BASE_URL is required for the production browser gate.",
  );
}

const baseURL = new URL(baseUrlValue);
if (baseURL.protocol !== "https:") {
  throw new Error("PLAYWRIGHT_PRODUCTION_BASE_URL must use https.");
}
if (
  baseURL.hostname === "localhost" ||
  baseURL.hostname === "127.0.0.1" ||
  baseURL.hostname === "::1" ||
  baseURL.hostname.endsWith(".localhost")
) {
  throw new Error(
    "PLAYWRIGHT_PRODUCTION_BASE_URL must target a production-shaped remote deployment.",
  );
}

const captureSuccessScreenshots =
  process.env.PLAYWRIGHT_CAPTURE_SUCCESS_SCREENSHOTS === "true";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "production-smoke.spec.ts",
  fullyParallel: false,
  forbidOnly: true,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: baseURL.toString(),
    screenshot: captureSuccessScreenshots ? "on" : "only-on-failure",
    trace: "on-first-retry",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "production-chromium" }],
});
