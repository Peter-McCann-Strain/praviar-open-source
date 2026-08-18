import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

const ANALYSES = [
  {
    id: "ana_e2e_001",
    compound_input: "aspirin",
    compound_name: "Aspirin",
    compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: "high",
    blocking_patents_count: 2,
    total_patents_found: 15,
    executive_summary:
      "Two blocking patent families require counsel review before launch.",
    estimated_cost_usd: 4.2,
    pipeline_duration_seconds: 320,
    flagged_for_review: true,
    review_status: {
      status: "under_review",
      is_persisted: true,
      note: "Counsel review queued",
      reviewer_name: "Demo Counsel",
      reviewer_email: "counsel@example.test",
      reviewed_at: null,
      updated_at: "2026-03-22T12:00:00Z",
    },
    share_active: true,
    share_view_count: 3,
    share_last_viewed_at: "2026-03-22T12:00:00Z",
    created_at: "2026-03-20T12:00:00Z",
    updated_at: "2026-03-22T12:00:00Z",
  },
  {
    id: "ana_e2e_002",
    compound_input: "ibuprofen",
    compound_name: "Ibuprofen",
    compound_smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    status: "running",
    current_step: 3,
    progress_pct: 38,
    overall_risk: "medium",
    blocking_patents_count: 0,
    total_patents_found: 8,
    executive_summary: "Triage in progress.",
    estimated_cost_usd: 2.1,
    pipeline_duration_seconds: null,
    flagged_for_review: false,
    review_status: null,
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: "2026-03-21T12:00:00Z",
    updated_at: "2026-03-21T12:05:00Z",
  },
] as const;

function buildStatusCounts(items: ReadonlyArray<{ status: string }>) {
  return {
    all: items.length,
    pending: items.filter((item) => item.status === "pending").length,
    running: items.filter((item) => item.status === "running").length,
    completed: items.filter((item) => item.status === "completed").length,
    failed: items.filter((item) => item.status === "failed").length,
    cancelled: items.filter((item) => item.status === "cancelled").length,
  };
}

async function mockAnalysesApis(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("praviar_tour_complete", "true");
  });

  await page.route("**/api/v1/analyses**", async (route) => {
    const url = new URL(route.request().url());
    const search = url.searchParams.get("search")?.toLowerCase().trim() ?? "";
    if (search.length > 200) {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Search query too long" }),
      });
      return;
    }
    const items = search
      ? ANALYSES.filter(
          (item) =>
            item.compound_name.toLowerCase().includes(search) ||
            item.compound_input.toLowerCase().includes(search),
        )
      : [...ANALYSES];

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items,
        total: items.length,
        page: 1,
        per_page: 20,
        status_counts: buildStatusCounts(items),
      }),
    });
  });
}

test.describe("Analyses List", () => {
  test.beforeEach(async ({ page }) => {
    await mockAnalysesApis(page);
    await page.goto("/analyses");
  });

  test("renders page title", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();
  });

  test("displays analyses table with column headers", async ({ page }) => {
    const table = page.locator("table");
    await expect(table).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Compound" }),
    ).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Status" }),
    ).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Risk" }),
    ).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Review" }),
    ).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "Patents" }),
    ).toBeVisible();
  });

  test("table displays demo data rows", async ({ page }) => {
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test("search input is present", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();
  });

  test("status filter dropdown has options", async ({ page }) => {
    const select = page.locator("select").first();
    await expect(select).toBeVisible();
    await expect(select.locator("option")).toHaveCount(6);
  });

  test("shows analysis count summary", async ({ page }) => {
    await expect(
      page.getByRole("status").filter({
        hasText: /Showing \d+-\d+ of \d+ analyses/,
      }),
    ).toBeVisible();
  });

  test("search filtering works", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill("zzz_nonexistent_compound");
    // Should show empty state or no matching rows
    await expect(page.getByText(/no analyses match/i)).toBeVisible();
  });

  test("clear filters restores all results", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill("zzz_nonexistent_compound");
    await expect(page.getByText(/no analyses match/i)).toBeVisible();

    const clearBtn = page.getByRole("button", { name: /clear filters/i });
    await clearBtn.click();
    await expect(page.locator("table tbody tr").first()).toBeVisible();
  });

  test("keeps long active filter chips contained on narrow screens", async ({
    page,
  }) => {
    const longQuery = `InChI=1S/${"C".repeat(180)}-patent-family-token`;
    const clampedQuery = longQuery.slice(0, 200);

    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(
      `/analyses?q=${encodeURIComponent(longQuery)}&status=completed&risk=high&sort=risk-desc`,
    );

    await expect(
      page.getByRole("list", { name: "Active filters" }),
    ).toBeVisible();
    await expect(
      page.getByRole("listitem", { name: `Search: ${clampedQuery}` }),
    ).toBeVisible();

    const layout = await page.evaluate(() => ({
      overflow:
        Math.max(
          document.body.scrollWidth,
          document.documentElement.scrollWidth,
        ) - window.innerWidth,
    }));

    expect(layout.overflow).toBeLessThanOrEqual(1);
  });
});

test.describe("New Analysis Wizard", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/analyses/new");
  });

  test("renders compound input area", async ({ page }) => {
    await expect(page.getByText(/compound/i).first()).toBeVisible();
  });

  test("accepts compound text input", async ({ page }) => {
    const input = page.locator("input, textarea").first();
    await input.fill("aspirin");
    await expect(input).toHaveValue("aspirin");
  });

  test("presents one adaptive launch path", async ({ page }) => {
    const input = page.locator("input, textarea").first();
    await input.fill("aspirin");
    await page.getByRole("button", { name: /Next: Configure/i }).click();

    await expect(page.getByText("Adaptive Execution")).toBeVisible();
    await expect(page.getByText("One adaptive path")).toBeVisible();
    await expect(page.getByText("Evidence gates")).toBeVisible();
    await expect(page.getByText(/Quick Scan|Standard|Thorough/)).toHaveCount(0);
  });
});

test.describe("Retired Quick Check route", () => {
  test("redirects without carrying legacy compound text in the URL", async ({
    page,
  }) => {
    await page.goto("/analyses/quick?compound=succinic%20acid");

    await expect(page).toHaveURL(/\/analyses\/new$/);
    expect(new URL(page.url()).searchParams.has("compound")).toBe(false);
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();
    await expect(page.getByLabel("Compound input")).toHaveValue("");
    await expect(page.getByText(/Quick Check|Check Now/)).toHaveCount(0);
  });
});
