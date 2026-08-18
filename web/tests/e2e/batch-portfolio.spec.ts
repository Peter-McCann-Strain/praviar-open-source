import { expect, test } from "./fixtures/strict-test";

test("batch page exposes the diligence portfolio workspace", async ({
  page,
}) => {
  await page.route("**/api/v1/batch?page=1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "batch-e2e-succinic",
            name: "Succinic acid — Counsel review required",
            total_compounds: 12,
            completed_count: 10,
            failed_count: 0,
            status: "running",
            analysis_ids: ["ana_demo_001"],
            created_at: "2026-04-24T10:00:00.000Z",
            updated_at: "2026-04-24T10:03:00.000Z",
          },
          {
            id: "batch-e2e-aspirin",
            name: "Aspirin — Founder brief ready",
            total_compounds: 8,
            completed_count: 8,
            failed_count: 0,
            status: "completed",
            analysis_ids: ["ana_demo_003"],
            created_at: "2026-04-23T10:00:00.000Z",
            updated_at: "2026-04-23T10:03:00.000Z",
          },
        ],
        total: 2,
      }),
    });
  });

  await page.goto("/batch");

  await expect(
    page.locator("h1", { hasText: "Diligence portfolio workspace" }),
  ).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator("tr", { hasText: "Succinic acid" })).toHaveCount(1);
  await expect(page.locator("tr", { hasText: "Aspirin" })).toHaveCount(1);
  await expect(
    page.locator("tr", { hasText: "Counsel review required" }),
  ).toHaveCount(1);
  await expect(
    page.locator("tr", { hasText: "Founder brief ready" }),
  ).toHaveCount(1);

  await expect(
    page.locator(
      'a[href="/analyses/ana_demo_001/report?audience=diligence&ai_context=review_questions&tab=claims"]',
    ),
  ).toHaveCount(1);
  await expect(
    page.locator(
      'a[href="/analyses/ana_demo_003/report?audience=diligence&ai_context=review_questions&tab=claims"]',
    ),
  ).toHaveCount(1);

  const hasHorizontalOverflow = await page.evaluate(() => {
    return (
      document.documentElement.scrollWidth >
      document.documentElement.clientWidth + 1
    );
  });
  expect(hasHorizontalOverflow).toBe(false);
});
