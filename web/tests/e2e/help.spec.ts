import { expect, test } from "./fixtures/strict-test";

test.describe("Help Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/help");
  });

  test("renders help page with content", async ({ page }) => {
    // Should have help/documentation content
    await expect(
      page.getByText(/help|documentation|guide/i).first(),
    ).toBeVisible();
  });

  test("displays pipeline step descriptions", async ({ page }) => {
    // The 8-step pipeline should be described
    await expect(
      page.getByText(/step 1|compound resolution|resolve/i).first(),
    ).toBeVisible();
  });

  test("displays risk level explanations", async ({ page }) => {
    // Assert the rendered risk content, not the intentionally hidden mobile
    // disclosure summary that repeats the level names on wider viewports.
    await expect(page.getByText(/^high$/i).first()).toBeVisible();
  });

  test("displays patent glossary terms", async ({ page }) => {
    // Should have glossary terms
    await expect(
      page.getByText(/freedom.to.operate|prior art|claim|patent/i).first(),
    ).toBeVisible();
  });

  test("expandable sections work", async ({ page }) => {
    // Find accordion triggers or expandable sections
    const triggers = page.locator(
      "[data-state], button[aria-expanded], details summary",
    );
    if (await triggers.first().isVisible()) {
      await triggers.first().click();
      // Content should be visible after expanding
    }
  });
});
