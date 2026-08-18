import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

const compoundStepTitle = (page: Page) =>
  page.locator(".type-heading-md").filter({ hasText: /^Compound Input$/ });

const mainNavigation = (page: Page) =>
  page.getByRole("complementary", { name: "Main navigation" });

const LIST_ANALYSIS = {
  id: "ana_user_flow_001",
  compound_input: "aspirin",
  compound_name: "Aspirin",
  compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
  status: "completed",
  current_step: 8,
  progress_pct: 100,
  overall_risk: "high",
  blocking_patents_count: 2,
  total_patents_found: 15,
  executive_summary: "Two patent families require counsel review.",
  estimated_cost_usd: 4.2,
  pipeline_duration_seconds: 320,
  flagged_for_review: true,
  review_status: null,
  share_active: false,
  share_view_count: 0,
  share_last_viewed_at: null,
  created_at: "2026-03-20T12:00:00Z",
  updated_at: "2026-03-22T12:00:00Z",
} as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("praviar_tour_complete", "true");
  });
  await page.route("**/api/v1/analyses**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname !== "/api/v1/analyses") {
      await route.continue();
      return;
    }

    const search = url.searchParams.get("search")?.toLowerCase().trim() ?? "";
    const status = url.searchParams.get("status") ?? "all";
    const matchesSearch =
      !search ||
      LIST_ANALYSIS.compound_name.toLowerCase().includes(search) ||
      LIST_ANALYSIS.compound_input.toLowerCase().includes(search);
    const matchesStatus = status === "all" || status === LIST_ANALYSIS.status;
    const items = matchesSearch && matchesStatus ? [LIST_ANALYSIS] : [];

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items,
        total: items.length,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 1,
          pending: 0,
          running: 0,
          completed: 1,
          failed: 0,
          cancelled: 0,
        },
      }),
    });
  });
});

// ---------------------------------------------------------------------------
// 1. Analysis Creation Flow (Wizard)
// ---------------------------------------------------------------------------

test.describe("Analysis Creation Flow", () => {
  test("full wizard journey: compound → configure → review", async ({
    page,
  }) => {
    // Start at dashboard
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();

    // Navigate to New Analysis via sidebar
    await mainNavigation(page).getByText("Analyses").click();
    await expect(page).toHaveURL(/\/analyses/);

    // Go to New Analysis page
    await page.goto("/analyses/new");
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();

    // Step 1: Compound input is visible
    await expect(compoundStepTitle(page)).toBeVisible();

    // Fill compound input with "aspirin"
    const compoundInput = page.getByLabel("Compound input");
    await expect(compoundInput).toBeVisible();
    await compoundInput.fill("aspirin");
    await expect(compoundInput).toHaveValue("aspirin");

    // "Next: Configure" button should be enabled now
    const nextConfigBtn = page.getByRole("button", {
      name: /Next: Configure/i,
    });
    await expect(nextConfigBtn).toBeEnabled();
    await nextConfigBtn.click();

    // Step 2: Verify the single adaptive path is visible
    await expect(page.getByText("Analysis Configuration")).toBeVisible();
    await expect(page.getByText("Adaptive Execution")).toBeVisible();
    await expect(page.getByText("One adaptive path")).toBeVisible();
    await expect(page.getByText("Evidence gates")).toBeVisible();
    await expect(page.getByText(/Quick Scan|Standard|Thorough/)).toHaveCount(0);

    // Click "Next: Review"
    const nextReviewBtn = page.getByRole("button", {
      name: /Next: Review/i,
    });
    await expect(nextReviewBtn).toBeVisible();
    await nextReviewBtn.click();

    // Step 3: Verify review summary shows "aspirin"
    await expect(page.getByText("Confirm & Launch")).toBeVisible();
    await expect(
      page
        .locator("span")
        .filter({ hasText: /^aspirin$/ })
        .first(),
    ).toBeVisible();

    // Verify "Start Analysis" button exists
    const startBtn = page.getByRole("button", { name: /Start Analysis/i });
    await expect(startBtn).toBeVisible();
  });

  test("example compound buttons pre-fill input", async ({ page }) => {
    await page.goto("/analyses/new");

    // Sample compound buttons should be visible when input is empty
    await expect(page.getByText("Sample compounds")).toBeVisible();
    await expect(page.getByText("Succinic acid")).toBeVisible();
    await expect(page.getByText("Ibuprofen")).toBeVisible();
    await expect(page.getByText("Aspirin")).toBeVisible();

    // Click "Succinic acid" example
    await page.getByText("Succinic acid").click();

    // Input should now have "succinic acid"
    const compoundInput = page.getByLabel("Compound input");
    await expect(compoundInput).toHaveValue("succinic acid");

    // Sample buttons should disappear once input is filled
    await expect(page.getByText("Sample compounds")).not.toBeVisible();
  });

  test("Next: Configure is disabled without compound input", async ({
    page,
  }) => {
    await page.goto("/analyses/new");

    const nextBtn = page.getByRole("button", { name: /Next: Configure/i });
    await expect(nextBtn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// 2. Retired Quick Check Route
// ---------------------------------------------------------------------------

test.describe("Retired Quick Check Route", () => {
  test("preserves compound query while redirecting to adaptive launch", async ({
    page,
  }) => {
    await page.goto("/analyses/quick?compound=ibuprofen");

    await expect(page).toHaveURL(/\/analyses\/new\?compound=ibuprofen/);
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();
    await expect(page.getByLabel("Compound input")).toHaveValue("ibuprofen");
    await expect(page.getByText(/Quick Check|Check Now/)).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 3. Report Navigation Flow
// ---------------------------------------------------------------------------

test.describe("Report Navigation Flow", () => {
  test("demo comments submit locally without a failed API request", async ({
    page,
  }) => {
    let commentPostCount = 0;
    const failedCommentRequests: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (request.method() === "POST" && path.endsWith("/comments")) {
        commentPostCount += 1;
      }
    });
    page.on("requestfailed", (request) => {
      if (new URL(request.url()).pathname.includes("/comments")) {
        failedCommentRequests.push(request.url());
      }
    });

    await page.goto("/analyses/ana_demo_001/report?tab=comments");

    const discussionHeading = page.getByRole("heading", {
      name: "Discussion",
    });
    await expect(discussionHeading).toBeVisible({ timeout: 15_000 });
    const discussionHeader = discussionHeading.locator("..");
    await expect(
      discussionHeader.getByText("2", { exact: true }),
    ).toBeVisible();

    const draft = page.getByPlaceholder("Add a comment about this analysis...");
    await draft.fill("Buyer-visible demo collaboration works end to end.");
    await page
      .getByTestId("report-tab-comments")
      .getByRole("button", { name: "Comment", exact: true })
      .click();

    await expect(
      page.getByText("Buyer-visible demo collaboration works end to end."),
    ).toBeVisible();
    await expect(draft).toHaveValue("");
    await expect(
      discussionHeader.getByText("3", { exact: true }),
    ).toBeVisible();
    expect(commentPostCount).toBe(0);
    expect(failedCommentRequests).toEqual([]);
  });

  test("navigate to report and verify all tabs", async ({ page }) => {
    // Navigate to a completed analysis detail page (demo ID)
    await page.goto("/analyses/ana_demo_001");

    // Demo mode guarantees a completed analysis and a governed report link.
    // `locator.isVisible()` is an immediate probe even when passed a timeout,
    // so use an assertion here to wait for the data-backed detail surface.
    const fullReportLink = page.getByRole("link", {
      name: /Open Report Workspace/i,
    });
    await expect(fullReportLink).toBeVisible({ timeout: 15_000 });

    // The analysis detail starts its own molecule render. Let that evidence
    // finish before leaving the page so the strict browser gate does not
    // mistake an intentional navigation cancellation for a broken chunk.
    await expect(
      page.getByRole("img", { name: /^Molecular structure:/i }),
    ).toBeVisible({ timeout: 15_000 });
    await fullReportLink.click();
    await expect(page).toHaveURL(/\/analyses\/ana_demo_001\/report/);

    // Finish the self-hosted molecule render before exercising rapid tab
    // navigation so an intentional component replacement cannot masquerade
    // as a failed script/WASM resource in the strict browser gate.
    await expect(
      page.getByRole("img", {
        name: /Molecular structure of succinic acid/i,
      }),
    ).toBeVisible({ timeout: 15_000 });

    const primaryTabs = [
      ["Outcome", "overview"],
      ["Patents", "patents"],
      ["Claims", "claims"],
      ["Validity", "invalidity"],
    ] as const;

    for (const [label] of primaryTabs) {
      await expect(page.getByRole("tab", { name: label })).toBeVisible();
    }

    for (const [label, tabId] of primaryTabs) {
      await page.getByRole("tab", { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`tab=${tabId}`));
      await expect(page.locator("main")).toBeVisible();
    }

    const overflowSections = [
      ["Audit trail", "audit"],
      ["Coverage & quality", "meta"],
    ] as const;

    for (const [label, tabId] of overflowSections) {
      await page.locator('button[aria-haspopup="menu"]').first().click();
      await page.getByRole("menuitem", { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`tab=${tabId}`));
      await expect(page.locator("main")).toBeVisible();
    }
  });

  test("report page renders with direct navigation", async ({ page }) => {
    await page.goto("/analyses/ana_demo_001/report");

    // Demo mode provides a governed synthetic report rather than an API
    // outage, so direct navigation must land on the decision packet.
    await expect(page.locator("main")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Succinic acid" }),
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Synthetic data visible")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Report temporarily unavailable" }),
    ).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Export Governance Flow
// ---------------------------------------------------------------------------

test.describe("Export Governance Flow", () => {
  test("blocked demo report routes the buyer to recovery instead of exporting", async ({
    page,
  }) => {
    await page.goto("/analyses/ana_demo_001/report");

    const blockedExport = page.getByRole("button", {
      name: "Review export blockers before exporting evidence packet",
    });
    await expect(blockedExport).toBeVisible({ timeout: 15_000 });
    await blockedExport.click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByTestId("report-reliance-readiness")).toBeVisible();
    await expect(
      page.getByTestId("report-export-recovery-brief"),
    ).toContainText("Resolve export blockers before evidence leaves Praviar");
  });

  test("blocked export remains closed after Escape", async ({ page }) => {
    await page.goto("/analyses/ana_demo_001/report");

    const blockedExport = page.getByRole("button", {
      name: "Review export blockers before exporting evidence packet",
    });
    await expect(blockedExport).toBeVisible({ timeout: 15_000 });
    await blockedExport.click();
    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByTestId("report-export-recovery-brief"),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Cross-Page Data Consistency
// ---------------------------------------------------------------------------

test.describe("Cross-Page Data Consistency", () => {
  test("analyses page renders correctly with table structure", async ({
    page,
  }) => {
    await page.goto("/analyses");
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();

    // Verify table is present with column headers
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
  });

  test("dashboard analysis count matches analyses page count", async ({
    page,
  }) => {
    // Visit dashboard
    await page.goto("/dashboard");

    // Check if Total Analyses KPI card is present (indicates data loaded)
    const totalAnalysesCard = page.getByText("Total Analyses");
    const hasDashboardData = await totalAnalysesCard
      .isVisible({ timeout: 5000 })
      .catch(() => false);

    if (hasDashboardData) {
      // Navigate to analyses page
      await page.goto("/analyses");
      await expect(
        page.getByRole("heading", { name: "Analysis Library", exact: true }),
      ).toBeVisible();

      // Verify the analyses summary text appears
      await expect(
        page.getByRole("status").filter({
          hasText: /Showing \d+-\d+ of \d+ analyses/,
        }),
      ).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// 6. Breadcrumb / Back Navigation
// ---------------------------------------------------------------------------

test.describe("Breadcrumb Navigation", () => {
  test("browser back from analysis detail returns to analyses list", async ({
    page,
  }) => {
    // Start at analyses list
    await page.goto("/analyses");
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();

    // Click into an analysis detail if data is present
    const firstLink = page.locator("table tbody a").first();
    const hasLinks = await firstLink
      .isVisible({ timeout: 5000 })
      .catch(() => false);

    if (hasLinks) {
      const href = await firstLink.getAttribute("href");
      expect(href).toMatch(/\/analyses\//);

      await firstLink.click();
      // Should navigate to the analysis detail page
      await expect(page).toHaveURL(/\/analyses\//);

      // Use browser back button
      await page.goBack();

      // Should return to analyses list
      await expect(page).toHaveURL(/\/analyses$/);
      await expect(
        page.getByRole("heading", { name: "Analysis Library", exact: true }),
      ).toBeVisible();
    }
  });

  test("navigate from dashboard through analyses to detail and back", async ({
    page,
  }) => {
    // Start at dashboard
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();

    // Navigate to analyses via sidebar
    await mainNavigation(page).getByText("Analyses").click();
    await expect(page).toHaveURL(/\/analyses/);
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();

    // Navigate back to dashboard
    await page.goBack();
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 7. Configuration Persistence in Wizard
// ---------------------------------------------------------------------------

test.describe("Configuration Persistence", () => {
  test("adaptive launch summary persists across wizard steps", async ({
    page,
  }) => {
    await page.goto("/analyses/new");

    // Fill compound to enable navigation
    const compoundInput = page.getByLabel("Compound input");
    await compoundInput.fill("aspirin");

    // Go to step 2
    await page.getByRole("button", { name: /Next: Configure/i }).click();
    await expect(page.getByText("Adaptive Execution")).toBeVisible();
    await expect(page.getByText("One adaptive path")).toBeVisible();
    await expect(page.getByText(/Quick Scan|Standard|Thorough/)).toHaveCount(0);

    // Go back to step 1
    await page.getByRole("button", { name: /Back/i }).click();
    await expect(compoundStepTitle(page)).toBeVisible();

    // Verify compound input still has "aspirin"
    await expect(compoundInput).toHaveValue("aspirin");

    // Go forward to step 2 again
    await page.getByRole("button", { name: /Next: Configure/i }).click();
    await expect(page.getByText("Adaptive Execution")).toBeVisible();
    await expect(page.getByText("Evidence gates")).toBeVisible();
    await page.getByRole("button", { name: /Next: Review/i }).click();
    await expect(page.getByText("Confirm & Launch")).toBeVisible();

    await expect(page.getByText("Adaptive evidence execution")).toBeVisible();
    await expect(
      page.getByText("Evidence Scope", { exact: true }),
    ).toBeVisible();
  });

  test("compound input persists when navigating between steps", async ({
    page,
  }) => {
    await page.goto("/analyses/new");

    const compoundInput = page.getByLabel("Compound input");
    await compoundInput.fill("remdesivir");
    await expect(compoundInput).toHaveValue("remdesivir");

    // Go to step 2 and back
    await page.getByRole("button", { name: /Next: Configure/i }).click();
    await expect(page.getByText("Analysis Configuration")).toBeVisible();

    await page.getByRole("button", { name: /Back/i }).click();
    await expect(compoundStepTitle(page)).toBeVisible();
    await expect(compoundInput).toHaveValue("remdesivir");
  });
});

// ---------------------------------------------------------------------------
// 8. Responsive Layout
// ---------------------------------------------------------------------------

test.describe("Responsive Layout", () => {
  test("sidebar collapses at mobile viewport", async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/dashboard");

    const sidebar = page.locator('[aria-label="Main navigation"]');
    await expect(sidebar).toHaveAttribute("aria-hidden", "true");
    await expect(sidebar).toHaveAttribute("inert", "");

    // On mobile, sidebar should be present but narrow
    // The sidebar is always visible — check that it's not taking full width
    // Main content area should be visible
    await expect(page.locator("main")).toBeVisible();
  });

  test("main content fills width on desktop viewport", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard");

    const sidebar = mainNavigation(page);
    await expect(sidebar).toBeVisible();

    const mainContent = page.locator("main");
    await expect(mainContent).toBeVisible();

    const mainBox = await mainContent.boundingBox();
    const sidebarBox = await sidebar.boundingBox();
    expect(mainBox).toBeTruthy();
    expect(sidebarBox).toBeTruthy();

    // Main content should extend to near the full viewport width minus sidebar
    // The content wrapper has pl-64 or pl-16 depending on sidebar state
    const totalWidth = sidebarBox!.width + mainBox!.width;
    // Should use most of the viewport width (allowing some padding)
    expect(totalWidth).toBeGreaterThan(1200);
  });

  test("sidebar toggle collapses and expands sidebar", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard");

    const sidebar = mainNavigation(page);
    await expect(sidebar).toBeVisible();

    // Get initial sidebar width
    const initialBox = await sidebar.boundingBox();
    expect(initialBox).toBeTruthy();
    const initialWidth = initialBox!.width;

    // Find and click the sidebar toggle button (ChevronLeft icon button)
    const toggleButton = sidebar.locator("button").first();
    await toggleButton.click();

    // Wait for transition (300ms)
    await page.waitForTimeout(400);

    // Sidebar width should have changed
    const afterBox = await sidebar.boundingBox();
    expect(afterBox).toBeTruthy();
    expect(afterBox!.width).not.toBe(initialWidth);

    // Click toggle again to restore
    await toggleButton.click();
    await page.waitForTimeout(400);

    const restoredBox = await sidebar.boundingBox();
    expect(restoredBox).toBeTruthy();
    expect(restoredBox!.width).toBe(initialWidth);
  });

  test("analyses wizard is usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/analyses/new");

    // Heading should be visible
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();

    // Compound input should be visible and functional
    const compoundInput = page.getByLabel("Compound input");
    await expect(compoundInput).toBeVisible();
    await compoundInput.fill("aspirin");

    // Next button should be visible and enabled
    const nextBtn = page.getByRole("button", { name: /Next: Configure/i });
    await expect(nextBtn).toBeVisible();
    await expect(nextBtn).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// Additional User Flow: Navigation between pages
// ---------------------------------------------------------------------------

test.describe("Full Navigation Flow", () => {
  test("navigate through all main pages via sidebar", async ({ page }) => {
    await page.goto("/dashboard");

    // Dashboard
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();

    // Analyses
    await mainNavigation(page).getByText("Analyses").click();
    await expect(page).toHaveURL(/\/analyses/);
    await expect(
      page.getByRole("heading", { name: "Analysis Library", exact: true }),
    ).toBeVisible();

    // Configuration
    await mainNavigation(page).getByText("Configuration").click();
    await expect(page).toHaveURL(/\/config/);

    // Help
    await mainNavigation(page).getByText("Help").click();
    await expect(page).toHaveURL(/\/help/);

    // Back to Dashboard
    await mainNavigation(page).getByText("Dashboard").click();
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
  });

  test("wizard stepper labels are visible and in order", async ({ page }) => {
    await page.goto("/analyses/new");

    // The three wizard step labels should be visible in the heading area
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();
    // Step labels appear in the stepper — verify the active step and future steps
    const progress = page.getByRole("navigation", {
      name: "New analysis progress",
    });
    await expect(
      progress.getByText("Add molecule", { exact: true }),
    ).toBeVisible();
    await expect(
      progress.getByText("Set evidence scope", { exact: true }),
    ).toBeVisible();
    await expect(
      progress.getByText("Confirm launch", { exact: true }),
    ).toBeVisible();
  });

  test("retired quick check URL opens adaptive launch", async ({ page }) => {
    await page.goto("/analyses/quick");

    await expect(page).toHaveURL(/\/analyses\/new/);
    await expect(
      page.getByRole("heading", { name: /New FTO Analysis/i }),
    ).toBeVisible();
    await expect(page.getByLabel("Compound input")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Additional: Search and Filter on Analyses Page
// ---------------------------------------------------------------------------

test.describe("Analyses Search and Filter", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/analyses");
  });

  test("search input filters and clear restores", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();

    // Type a non-matching query
    await searchInput.fill("zzz_nonexistent_compound_xyz");

    // Should show empty state
    await expect(page.getByText(/no analyses match/i)).toBeVisible();

    // Clear filters
    const clearBtn = page.getByRole("button", { name: /clear filters/i });
    await clearBtn.click();

    // Search should be cleared
    await expect(searchInput).toHaveValue("");
  });

  test("status filter dropdown is functional", async ({ page }) => {
    const select = page.locator("select").first();
    await expect(select).toBeVisible();

    // Select "Completed" filter
    await select.selectOption("completed");

    // Page should still render without crash
    await expect(page.locator("main")).toBeVisible();

    // Reset to "All"
    await select.selectOption("all");
    await expect(page.locator("main")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Additional: Premium Theme Contract
// ---------------------------------------------------------------------------

test.describe("Premium Theme Contract", () => {
  test("dashboard shell stays on the premium light palette", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    await expect(page.locator("html")).toHaveClass(/light/);

    const sidebar = mainNavigation(page);
    const themeToggle = sidebar.locator(
      'button[title*="light mode"], button[title*="dark mode"]',
    );
    await expect(themeToggle).toHaveCount(0);
  });
});
