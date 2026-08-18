import { defineConfig, devices } from "@playwright/test";
import { parseStagingJourneyEnvironment } from "./tests/e2e/fixtures/staging-journey-gate";

const staging = parseStagingJourneyEnvironment(process.env);

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "staging-critical-journeys.spec.ts",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["line"]],
  outputDir: "test-results/staging-critical-journeys",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: staging.baseURL,
    // Success screenshots are attached explicitly only after the synthetic
    // launched report is loaded. Automatic screenshots could capture a
    // password field if sign-in fails, so keep them disabled here.
    screenshot: "off",
    // Retain diagnostics locally on a failed attempt. The workflow uploads the
    // output directory only on success, so traces/videos containing Clerk
    // cookies or bearer headers never become CI artifacts.
    trace: "retain-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "staging-critical-chromium" }],
});
