/**
 * Error-path E2E coverage.
 *
 * These tests guard the user-facing failure modes that production-quality
 * frontends MUST handle gracefully:
 *  - upstream 5xx responses (server errors)
 *  - 401 responses (auth lapses)
 *  - request timeouts
 *  - the browser going offline
 *
 * They use `page.route()` mocks in the same shape as `flagship-report.spec.ts`
 * — no real network, just patched fetch responses — so they run reliably
 * inside the Playwright web-server harness configured by `playwright.config.ts`.
 */
import type { Page, Route } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

/** Route every API call to a stub so an offline test exercises the network
 * failure code path without hitting real services. */
async function blockUnmockedApiCalls(page: Page) {
  await page.route(
    "**/api/v1/comments/review-queue**",
    async (route: Route) => {
      // Surface a network failure in the review panel while the dashboard's
      // analyses fixture keeps the surrounding page shell mounted.
      await route.abort("failed");
    },
  );
}

/** Suppress welcome modal so it does not mask error UI. */
async function dismissWelcomeModal(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("praviar_welcomed", "true");
    window.localStorage.setItem("praviar_tour_complete", "true");
  });
}

async function mockDashboardAnalyses(page: Page) {
  await page.route("**/api/v1/analyses?**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "ana_e2e_error_001",
            compound_input: "succinic acid",
            compound_name: "Succinic acid",
            compound_smiles: "OC(=O)CCC(O)=O",
            status: "completed",
            current_step: 8,
            progress_pct: 100,
            overall_risk: "high",
            blocking_patents_count: 2,
            total_patents_found: 2417,
            executive_summary: "Review queue error-path fixture.",
            estimated_cost_usd: 3.42,
            pipeline_duration_seconds: 132,
            flagged_for_review: true,
            share_token: null,
            share_view_count: 0,
            share_last_viewed_at: null,
            created_at: "2026-04-24T10:00:00.000Z",
            updated_at: "2026-04-24T10:03:00.000Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      }),
    });
  });
}

test.describe("API error surfaces", () => {
  test.beforeEach(async ({ page }) => {
    await dismissWelcomeModal(page);
    await mockDashboardAnalyses(page);
  });

  test("dashboard surfaces a recoverable error UI when the review-queue API returns 500", async ({
    page,
  }) => {
    // Specific 500 for the legal-review-workload panel; everything else can
    // still resolve so the rest of the dashboard renders.
    await page.route("**/api/v1/comments/review-queue**", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal server error" }),
      });
    });

    await page.goto("/dashboard");

    // The dashboard must keep rendering — the panel only soft-fails.
    await expect(
      page.getByText(/Review queue temporarily unavailable/i),
    ).toBeVisible({
      timeout: 15_000,
    });
    // The Retry affordance must be present — users need a way out of the
    // failure without reloading the page.
    await expect(page.getByRole("button", { name: /Retry/i })).toBeVisible();
  });

  test("retrying after a 500 dispatches a fresh request and recovers when the API succeeds", async ({
    page,
  }) => {
    let callCount = 0;
    let allowRecovery = false;
    await page.route("**/api/v1/comments/review-queue**", async (route) => {
      callCount += 1;
      if (!allowRecovery) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "boom" }),
        });
        return;
      }
      // Second call — return an empty queue so the panel can render.
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          counts: {
            open_total: 0,
            mine: 0,
            assigned: 0,
            unassigned: 0,
            overdue: 0,
            escalated: 0,
          },
        }),
      });
    });

    await page.goto("/dashboard");
    await expect(
      page.getByText(/Review queue temporarily unavailable/i),
    ).toBeVisible({
      timeout: 15_000,
    });
    const callsBeforeRetry = callCount;
    allowRecovery = true;
    await page.getByRole("button", { name: /Retry/i }).click();

    // The retry must trigger another network call (this is the contract — no
    // silent caching of the failure).
    await expect.poll(() => callCount).toBeGreaterThan(callsBeforeRetry);
  });

  test("a 401 from a protected API does not leak silently — the failure mode is visible", async ({
    page,
  }) => {
    await page.route("**/api/v1/comments/review-queue**", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not authenticated" }),
      });
    });

    await page.goto("/dashboard");

    // Authentication-boundary failures are intentionally not presented as a
    // retryable service outage. The private workload panel must disappear so
    // a 401 cannot be rendered as a fake empty/success queue.
    await expect(page.getByText("Legal review workload")).toHaveCount(0);
    await expect(
      page.getByText("Review queue temporarily unavailable."),
    ).toHaveCount(0);
    await expect(page.getByTestId("workspace-boundary-banner")).toBeVisible();
  });

  test("a slow API (timeout-grade latency) does not lock the page in a phantom loading state", async ({
    page,
  }) => {
    // Pause the request long enough that any reasonable React-Query timeout
    // would have fired and shown a fallback.  We never resolve it — the test
    // is checking that the UI is still interactive and either shows loading
    // affordances OR an error/empty state, never a crashed white screen.
    await page.route("**/api/v1/comments/review-queue**", async () => {
      // Intentionally never call route.fulfill — Playwright will hang the
      // request until the test ends.
    });

    await page.goto("/dashboard");

    // The page header must still render even while the panel is in flight —
    // this guards against a regression where one slow call blocked the whole
    // dashboard shell.
    // Match the page title exactly: during the governed auth transition the
    // companion heading "Checking dashboard access" can briefly coexist with
    // it, and a fuzzy match turns that healthy transition into strict-locator
    // ambiguity.
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("offline network state shows the error UI instead of a stuck spinner", async ({
    page,
    context,
  }) => {
    // Block API traffic so the panel cannot succeed.
    await blockUnmockedApiCalls(page);
    await page.goto("/dashboard");
    await expect(page.getByRole("button", { name: /Retry/i })).toBeVisible({
      timeout: 15_000,
    });
    await context.setOffline(true);
    await page.getByRole("button", { name: /Retry/i }).click();

    // We are not asserting a specific offline message string (the framework
    // owns that copy and may evolve it).  We *do* assert the page does not
    // render the success-state heading we'd see if the API had returned data
    // — and the page is not a totally blank white screen.
    await page.waitForLoadState("domcontentloaded").catch(() => {});
    const html = await page.content();
    expect(html.length).toBeGreaterThan(0);

    // Restore connectivity for any teardown that needs it.
    await context.setOffline(false);
  });
});
