import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

async function mockAnalysesList(page: Page) {
  await page.route("**/api/v1/analyses?**", async (route) => {
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
}

test.describe("Navigation", () => {
  test("sidebar has all navigation items", async ({ page }) => {
    await page.goto("/dashboard");
    const sidebar = page.getByRole("complementary", {
      name: "Main navigation",
    });
    await expect(sidebar).toBeVisible();

    // Check nav links by their label text
    await expect(sidebar.getByText("Dashboard")).toBeVisible();
    await expect(sidebar.getByText("Analyses")).toBeVisible();
    await expect(sidebar.getByText("Configuration")).toBeVisible();
    await expect(sidebar.getByText("Help")).toBeVisible();
  });

  test("navigates to analyses page from sidebar", async ({ page }) => {
    await mockAnalysesList(page);
    await page.goto("/dashboard");
    await page
      .getByRole("complementary", { name: "Main navigation" })
      .getByText("Analyses")
      .click();
    await expect(page).toHaveURL(/\/analyses/);
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();
  });

  test("navigates to help page from sidebar", async ({ page }) => {
    await page.goto("/dashboard");
    await page
      .getByRole("complementary", { name: "Main navigation" })
      .getByText("Help")
      .click();
    await expect(page).toHaveURL(/\/help/);
  });

  test("navigates to config page from sidebar", async ({ page }) => {
    await page.goto("/dashboard");
    await page
      .getByRole("complementary", { name: "Main navigation" })
      .getByText("Configuration")
      .click();
    await expect(page).toHaveURL(/\/config/);
  });

  test("landing page has Start Analysis link", async ({ page }) => {
    await page.goto("/");
    const startAnalysis = page
      .getByRole("link", { name: /start analysis/i })
      .first();
    await expect(startAnalysis).toBeVisible();
    await expect(startAnalysis).toHaveAttribute(
      "href",
      "/sign-up?return_to=%2Fanalyses%2Fnew",
    );
  });
});
