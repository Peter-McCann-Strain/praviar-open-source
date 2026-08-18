import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

async function mockEmptyDashboardApis(page: Page) {
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
}

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await mockEmptyDashboardApis(page);
    await page.goto("/dashboard");
  });

  test("renders page title and subtitle", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "FTO activity, review load, and high-risk findings in one operational view.",
      ),
    ).toBeVisible();
  });

  test("displays welcome empty state when no data", async ({ page }) => {
    await expect(page.getByText("Welcome to Praviar")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Start New Analysis" }),
    ).toBeVisible();
  });

  test("shows example compound buttons", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Succinic acid" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Ibuprofen" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Lactic acid" }),
    ).toBeVisible();
  });

  test("shows feature cards in empty state", async ({ page }) => {
    await expect(page.getByText("Patent Risk Map")).toBeVisible();
    await expect(page.getByText("Claim Analysis")).toBeVisible();
    await expect(page.getByText("Professional Report")).toBeVisible();
  });

  test("has Start New Analysis and Review Queue action buttons", async ({
    page,
  }) => {
    await expect(
      page.getByRole("link", { name: "Start New Analysis" }),
    ).toBeVisible();
    const reviewQueueLinks = page.getByRole("link", { name: "Review Queue" });
    await expect(reviewQueueLinks.first()).toBeVisible();
  });

  test("renders dashboard CTAs without nested interactive controls", async ({
    page,
  }) => {
    await expect(
      page.getByRole("link", { name: "Start New Analysis" }),
    ).toHaveAttribute("href", "/analyses/new");
    await expect(
      page.getByRole("link", { name: "Review Queue" }).first(),
    ).toHaveAttribute("href", "/reviews");

    const nestedInteractiveCount = await page.evaluate(
      () =>
        document.querySelectorAll(
          "a[href] button, button a[href], a[href] [role='button'], [role='button'] a[href], button button",
        ).length,
    );

    expect(nestedInteractiveCount).toBe(0);
  });
});
