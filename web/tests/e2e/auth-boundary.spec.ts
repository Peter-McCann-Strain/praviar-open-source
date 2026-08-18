import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import { TEST_REPORT } from "../../src/lib/demo-report";

// Use a non-demo identifier so this test exercises the intercepted private
// network path even when the explicit development auth bypass is enabled.
const ANALYSIS_ID = "ana_auth_boundary_001";

type AuthBoundaryTestWindow = Window & {
  __praviarE2EEmitAuthBoundaryChanged?: (detail?: {
    refreshToken?: boolean;
  }) => void;
  __praviarStaleSearchTextSeen?: boolean;
  __praviarStopStaleSearchObserver?: () => void;
};

async function mockReportPageApis(
  page: Page,
  delayedSearch: Promise<void>,
  onSearchRequested: () => void,
  onSearchFulfilled: () => void,
  onUnexpectedApiRequest: (request: string) => void,
) {
  // Register this first: Playwright evaluates routes in reverse registration
  // order, so every explicit endpoint below wins and any undeclared API call
  // fails closed inside the hermetic harness instead of reaching :18080.
  await page.route(
    (url) => url.pathname.startsWith("/api/v1/"),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      onUnexpectedApiRequest(`${request.method()} ${url.pathname}`);
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unexpected test API request" }),
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/v1/principal/capabilities",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          role: "attorney",
          can_create_analysis: false,
          can_view_patents: true,
          can_manage_monitors: false,
          can_view_review_queue: false,
          can_assign_review: false,
          can_resolve_review: false,
          can_escalate_review: false,
          can_create_batch: false,
          can_manage_config: false,
          can_export_report: false,
          can_share_report: false,
          can_deliver_report: false,
          can_view_billing: false,
          can_manage_billing: false,
          can_manage_api_keys: false,
          can_view_platform_admin: false,
          risk_ratings_restricted: false,
          api_key_report_export_scope_available: false,
        }),
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/v1/notifications/unread-count",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ unread_count: 0 }),
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/v1/notifications",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread_count: 0, total: 0 }),
      });
    },
  );

  await page.route(
    (url) => url.pathname === "/api/v1/analyses",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          per_page: 20,
          status_counts: {},
        }),
      });
    },
  );

  await page.route(
    (url) =>
      url.pathname ===
      `/api/v1/reports/${ANALYSIS_ID}/workspace-summary`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          analysis_id: ANALYSIS_ID,
          report_id: TEST_REPORT.report_id,
          trust_mode: "counsel",
          target_jurisdictions: ["US"],
          jurisdiction_matrix: [],
          report_summary: {
            overall_risk: "high",
            blocking_patents_count: 3,
            total_patents_found: 2417,
            executive_summary: TEST_REPORT.risk_summary.executive_summary,
          },
          capability_metadata: {},
          suggested_evidence_queries: [],
          monitor_seed_defaults: {
            analysis_id: ANALYSIS_ID,
            compound_name: "Succinic acid",
            compound_smiles: "OC(=O)CCC(O)=O",
            schedule: "weekly",
            source_report_id: TEST_REPORT.report_id,
            source_trust_mode: "counsel",
            requires_manual_input: false,
            missing_fields: [],
          },
          routing_profile: {},
          opinion_readiness: { export_ready: false },
          data_coverage: {},
          source_convergence: {},
          uncertainty_register: [],
          evidence_scope: {
            mode: "report_evidence",
            external_live_retrieval: false,
            comment_routing_available: true,
            sources_considered: [],
            governed_note: "Hermetic auth-boundary test fixture.",
            provider_capabilities: [],
            providers: [],
            hybrid_evidence_ready: false,
          },
        }),
      });
    },
  );

  await page.route(
    (url) =>
      url.pathname === `/api/v1/monitors/by-analysis/${ANALYSIS_ID}`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(null),
      });
    },
  );

  await page.route(`**/api/v1/reports/${ANALYSIS_ID}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(TEST_REPORT),
    });
  });

  await page.route(`**/api/v1/analyses/${ANALYSIS_ID}`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: ANALYSIS_ID,
        compound_input: "succinic acid",
        compound_name: "Succinic acid",
        compound_smiles: "OC(=O)CCC(O)=O",
        status: "completed",
        current_step: 8,
        progress_pct: 100,
        overall_risk: "high",
        blocking_patents_count: 3,
        total_patents_found: 2417,
        executive_summary: TEST_REPORT.risk_summary.executive_summary,
        estimated_cost_usd: 4.82,
        pipeline_duration_seconds: 842,
        flagged_for_review: true,
        share_token: "sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
        share_view_count: 12,
        share_last_viewed_at: "2026-04-09T11:24:00.000Z",
        created_at: "2026-04-08T14:22:13.100Z",
        updated_at: "2026-04-08T14:36:15.000Z",
      }),
    });
  });

  await page.route(
    `**/api/v1/comments?analysis_id=${ANALYSIS_ID}`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    },
  );

  await page.route("**/api/v1/comments/reviewers?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(
    `**/api/v1/analyses/${ANALYSIS_ID}/decisions`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: [],
          counts: { accept: 0, reject: 0, edit: 0 },
        }),
      });
    },
  );

  await page.route(
    `**/api/v1/analyses/${ANALYSIS_ID}/review-status`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          analysis_id: ANALYSIS_ID,
          status: "under_review",
          note: "Counsel review in progress.",
          reviewer_name: "Demo Counsel",
          reviewer_email: "counsel@example.test",
          reviewed_at: null,
          updated_at: "2026-04-24T10:00:00.000Z",
          decision_counts: { accept: 0, reject: 0, edit: 0 },
          findings_total: 4,
          findings_reviewed: 0,
          completion_pct: 0,
        }),
      });
    },
  );

  await page.route(`**/api/v1/reports/${ANALYSIS_ID}/search`, async (route) => {
    onSearchRequested();
    await delayedSearch;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        query: "private stale search",
        interpreted_query: "Late stale search result should not render",
        results: [
          {
            patent_id: "US-STALE-001",
            section: "claims",
            relevance: 0.99,
            snippet:
              "This private result belongs to the previous auth boundary.",
          },
        ],
        total: 1,
      }),
    });
    onSearchFulfilled();
  });
}

test.describe("auth boundary isolation", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("praviar_welcomed", "true");
      window.localStorage.setItem("praviar_tour_complete", "true");
    });
  });

  test("clears report UI and ignores a late private response after auth boundary change", async ({
    page,
  }) => {
    let releaseSearchResponse!: () => void;
    let searchWasRequested = false;
    let searchWasFulfilled = false;
    const unexpectedApiRequests: string[] = [];
    const delayedSearch = new Promise<void>((resolve) => {
      releaseSearchResponse = resolve;
    });

    await mockReportPageApis(
      page,
      delayedSearch,
      () => {
        searchWasRequested = true;
      },
      () => {
        searchWasFulfilled = true;
      },
      (request) => {
        unexpectedApiRequests.push(request);
      },
    );

    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    const reportHeading = page.getByRole("heading", {
      name: "succinic acid",
      exact: true,
    });
    await expect(reportHeading).toBeVisible({
      timeout: 15_000,
    });
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            typeof (window as AuthBoundaryTestWindow)
              .__praviarE2EEmitAuthBoundaryChanged,
        ),
      )
      .toBe("function");

    const searchInput = page.getByLabel("Search report");
    await page.evaluate(() => {
      const staleText = "Late stale search result should not render";
      const testWindow = window as AuthBoundaryTestWindow;
      testWindow.__praviarStaleSearchTextSeen =
        document.body.textContent?.includes(staleText) ?? false;

      const observer = new MutationObserver(() => {
        if (document.body.textContent?.includes(staleText)) {
          testWindow.__praviarStaleSearchTextSeen = true;
        }
      });
      observer.observe(document.body, {
        characterData: true,
        childList: true,
        subtree: true,
      });
      testWindow.__praviarStopStaleSearchObserver = () => observer.disconnect();
    });

    await searchInput.fill("private stale search");
    await expect.poll(() => searchWasRequested).toBe(true);

    await page.evaluate(() => {
      (window as AuthBoundaryTestWindow).__praviarE2EEmitAuthBoundaryChanged?.({
        refreshToken: false,
      });
    });

    await expect(
      page.getByRole("heading", { name: "Checking report access" }),
    ).toBeVisible();
    await expect(page.getByText("No report content exposed")).toBeVisible();
    await expect(searchInput).toBeHidden();
    await expect(reportHeading).toBeHidden();

    releaseSearchResponse();
    await expect.poll(() => searchWasFulfilled).toBe(true);
    await expect(
      page.getByText("Late stale search result should not render"),
    ).toBeHidden();
    await expect
      .poll(() =>
        page.evaluate(
          () => (window as AuthBoundaryTestWindow).__praviarStaleSearchTextSeen,
        ),
      )
      .toBe(false);
    await page.evaluate(() => {
      (window as AuthBoundaryTestWindow).__praviarStopStaleSearchObserver?.();
    });
    await expect(
      page.getByRole("heading", { name: "Checking report access" }),
    ).toBeVisible();
    await expect(page.getByText("No report content exposed")).toBeVisible();
    expect(unexpectedApiRequests).toEqual([]);
  });
});
