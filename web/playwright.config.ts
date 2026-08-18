import { defineConfig, devices } from "@playwright/test";
import {
  DEMO_ONBOARDING_IDENTITY,
  DEV_ONBOARDING_IDENTITY,
  onboardingStorageKeys,
} from "./src/lib/onboarding-storage";
const PORT = Number(process.env.PLAYWRIGHT_PORT ?? 3100);
const API_PORT = Number(process.env.PLAYWRIGHT_API_PORT ?? 18080);
const REUSE_EXISTING_SERVER =
  process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === "true";
const CAPTURE_SUCCESS_SCREENSHOTS =
  process.env.PLAYWRIGHT_CAPTURE_SUCCESS_SCREENSHOTS === "true";
const CHROME_EXECUTABLE_PATH = process.env.PLAYWRIGHT_CHROME_EXECUTABLE;
const DEV_ONBOARDING_STORAGE_KEYS = onboardingStorageKeys(
  DEV_ONBOARDING_IDENTITY,
);
const DEMO_ONBOARDING_STORAGE_KEYS = onboardingStorageKeys(
  DEMO_ONBOARDING_IDENTITY,
);

if (!DEV_ONBOARDING_STORAGE_KEYS || !DEMO_ONBOARDING_STORAGE_KEYS) {
  throw new Error("Playwright onboarding identities must produce scoped keys");
}

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: [
    "**/production-compound-canary.spec.ts",
    "**/production-smoke.spec.ts",
    "**/staging-critical-journeys.spec.ts",
  ],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }]],
  // Keep Playwright's automatically cleaned attachments outside the retained
  // visual-matrix evidence tree. The demo and API profiles run as separate
  // Playwright processes and must both survive for composite verification.
  outputDir: "test-results/playwright-artifacts",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
    screenshot: CAPTURE_SUCCESS_SCREENSHOTS ? "on" : "only-on-failure",
    // Pre-dismiss the WelcomeModal that auto-opens on first dashboard load.
    // Without this, every /dashboard navigation triggers a Radix Dialog
    // overlay that intercepts pointer events for ~7 of our specs. The key
    // is asserted in welcome-modal-constants.ts (`WELCOME_MODAL_STORAGE_KEY`).
    storageState: {
      cookies: [],
      origins: [
        {
          origin: `http://localhost:${PORT}`,
          localStorage: [
            { name: DEV_ONBOARDING_STORAGE_KEYS.welcome, value: "true" },
            { name: DEV_ONBOARDING_STORAGE_KEYS.tour, value: "true" },
            { name: DEMO_ONBOARDING_STORAGE_KEYS.welcome, value: "true" },
            { name: DEMO_ONBOARDING_STORAGE_KEYS.tour, value: "true" },
          ],
        },
      ],
    },
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: CHROME_EXECUTABLE_PATH
          ? { executablePath: CHROME_EXECUTABLE_PATH }
          : undefined,
      },
    },
  ],
  webServer: {
    // Dev mode is intentional: the production build enforces hardening checks
    // (NEXT_PUBLIC_APP_URL non-localhost, Clerk publishable key, etc.) that
    // aren't relevant to E2E coverage of user flows. Dev mode boots faster
    // and exercises the same rendering paths.
    //
    // NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS=true activates the proxy auth bypass
    // in src/proxy.ts (gated to nodeEnv !== production by production-env.ts
    // §allowsMissingClerkProtectedRouteBypass), letting protected routes
    // (/dashboard, /analyses, /help, /config) render in tests without a real
    // Clerk session. Production-environment safety is preserved because the
    // bypass is unreachable when NODE_ENV=production.
    // Use webpack for the evidence-bound matrix. Turbopack's persistent dev
    // cache can expand by multiple gigabytes while compiling 130 deliberately
    // distinct UI states, making the browser receipt depend on available disk
    // rather than application correctness. The webpack dev server exercises
    // the same application source without that unbounded evidence-run cache.
    command: `pnpm dev --webpack --hostname 127.0.0.1 --port ${PORT}`,
    // Probe a real static asset so server readiness is not coupled to a cold
    // compile of the entire marketing home route. Every captured application
    // route still has its own bounded navigation/readiness assertions.
    url: `http://127.0.0.1:${PORT}/brand/praviar-mark.svg`,
    reuseExistingServer: REUSE_EXISTING_SERVER,
    timeout: 180_000,
    env: {
      NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`,
      NEXT_PUBLIC_APP_URL: `http://localhost:${PORT}`,
      PLAYWRIGHT_API_PORT: String(API_PORT),
      NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "true",
      NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE: "true",
      NEXT_PUBLIC_DEMO_MODE:
        process.env.PLAYWRIGHT_DEMO_MODE === "true" ? "true" : "false",
    },
  },
});
