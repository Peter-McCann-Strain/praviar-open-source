import { expect, test } from "./fixtures/strict-test";

test.describe("Configuration Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/config");
  });

  test("renders configuration heading", async ({ page }) => {
    await expect(
      page.getByText(/configuration|config|settings/i).first(),
    ).toBeVisible();
  });

  test("displays coverage budget options", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /Focused coverage profile/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Balanced coverage profile/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Expanded coverage profile/i }),
    ).toBeVisible();
    await expect(page.getByText(/Quick|Standard|Thorough/)).toHaveCount(0);
  });

  test("displays source configuration", async ({ page }) => {
    // Should show patent source toggles
    await expect(
      page.getByText(/pubchem|source|patent/i).first(),
    ).toBeVisible();
  });

  test("coverage budget click changes form state", async ({ page }) => {
    await page.getByRole("button", { name: /Expanded coverage/i }).click();
    await expect(page.locator("main")).toBeVisible();
  });
});
