import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

async function mockResponsiveApis(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("praviar_tour_complete", "true");
  });

  await page.route("**/api/v1/analyses**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 0,
          pending: 0,
          running: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
        },
      }),
    });
  });

  await page.route("**/api/v1/notifications**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const body = pathname.endsWith("/unread-count")
      ? { unread_count: 0 }
      : { items: [], unread_count: 0, total: 0 };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.route("**/api/v1/api-keys**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "key_responsive_001",
            name: "Responsive QA automation",
            key_prefix: "prv_test_responsive",
            scopes: ["analyses:read", "reports:read"],
            expires_at: "2026-09-24T09:30:00.000Z",
            last_used_at: "2026-06-24T09:30:00.000Z",
            revoked: false,
            created_at: "2026-06-01T10:00:00.000Z",
          },
        ],
        total: 1,
      }),
    });
  });
}

test.describe("Responsive Layout", () => {
  test("dashboard renders on mobile viewport", async ({ page }) => {
    await mockResponsiveApis(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Welcome to Praviar")).toBeVisible();
  });

  test("analyses table renders on tablet viewport", async ({ page }) => {
    await mockResponsiveApis(page);
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/analyses");
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();
    await expect(page.locator("table")).toBeVisible();
  });

  test("settings API key ledger contains tablet overflow", async ({ page }) => {
    await mockResponsiveApis(page);
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "API key ledger" }),
    ).toBeVisible();

    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return (
        Math.max(root.scrollWidth, document.body.scrollWidth) - root.clientWidth
      );
    });

    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("dashboard renders on large screen", async ({ page }) => {
    await mockResponsiveApis(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Welcome to Praviar")).toBeVisible();
  });
});
