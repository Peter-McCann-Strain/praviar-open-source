import { defineConfig, devices } from "@playwright/test";
import { parseProductionCompoundCanaryEnvironment } from "./tests/e2e/fixtures/production-compound-canary-gate";

const production = parseProductionCompoundCanaryEnvironment(process.env);

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "production-compound-canary.spec.ts",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["line"]],
  outputDir: "test-results/production-compound-canary",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: production.baseURL,
    screenshot: "off",
    // Failure traces and videos remain only on the ephemeral runner.  The
    // deployment uploads evidence only after a successful, cleaned-up canary.
    trace: "retain-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [{ name: "production-compound-canary-chromium" }],
});
