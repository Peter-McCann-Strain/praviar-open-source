import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import { TEST_REPORT } from "../../src/lib/demo-report";

const ANALYSIS_ID = "ana_demo_001";
const REPORT_ROUTE = new RegExp(`/api/v1/reports/${ANALYSIS_ID}(?:\\?.*)?$`);

async function mockFlagshipWorkspaceApis(page: Page) {
  await page.route(REPORT_ROUTE, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(TEST_REPORT),
    });
  });

  await page.route(
    `**/api/v1/reports/${ANALYSIS_ID}/workspace-summary`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          analysis_id: ANALYSIS_ID,
          report_id: ANALYSIS_ID,
          trust_mode: "counsel",
          target_jurisdictions: ["US", "EP"],
          jurisdiction_matrix: [
            { jurisdiction: "US", risk: "high", blockers: 2 },
            { jurisdiction: "EP", risk: "medium", blockers: 1 },
          ],
          report_summary: {
            overall_risk: "high",
            blocking_patents_count: 3,
            total_patents_found: 2417,
            executive_summary:
              "Three material patent families need counsel review before launch.",
          },
          capability_metadata: {
            mode_label: "Counsel workspace",
            capability_label: "Report-grounded AI review",
            scope_label: "Succinic acid FTO case",
            source_coverage: "Report, claims, citations, monitor seed",
            evidence_mode: "Governed evidence search",
            monitor_state: "Monitoring actions allowed",
            tool_access: [
              "evidence-search",
              "review-handoff",
              "monitor",
              "export",
            ],
          },
          suggested_evidence_queries: [
            {
              kind: "risk",
              query: "succinate claim 1 blocking family",
              rationale: "Stress-test the lead blocker.",
              source: "workspace",
            },
          ],
          monitor_seed_defaults: {
            analysis_id: ANALYSIS_ID,
            compound_name: "Succinic acid",
            compound_smiles: "OC(=O)CCC(O)=O",
            schedule: "weekly",
            source_report_id: ANALYSIS_ID,
            source_trust_mode: "counsel",
            requires_manual_input: false,
            missing_fields: [],
          },
          routing_profile: {
            modality: "small_molecule",
            matter_type: "fto",
            flags: [],
          },
          opinion_readiness: {
            export_ready: false,
            summary:
              "Counsel export remains blocked until the selected jurisdictions are reviewed.",
            jurisdictions_blocking_export: ["US", "EP"],
          },
          data_coverage: {},
          source_convergence: {},
          uncertainty_register: [],
          evidence_scope: {
            mode: "report_evidence",
            external_live_retrieval: false,
            comment_routing_available: true,
            sources_considered: ["Report claims", "Patent citations"],
            governed_note: "Report-grounded evidence only for this demo run.",
            provider_capabilities: [],
            providers: [],
            hybrid_evidence_ready: false,
          },
        }),
      });
    },
  );

  await page.route(
    `**/api/v1/reports/${ANALYSIS_ID}/evidence-search`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          query: "succinate claim 1 blocking family",
          interpreted_query:
            "Lead blocker claim 1 mapped to succinate salt coverage",
          total: 1,
          scope: {
            mode: "report_evidence",
            external_live_retrieval: false,
            comment_routing_available: true,
            sources_considered: ["Report claims", "Patent citations"],
            governed_note: "Report-grounded evidence only.",
          },
          results: [
            {
              result_id: "ev-1",
              title: "US blocker claim 1 maps to succinate salt form",
              summary:
                "Claim language remains material for the proposed commercialization path.",
              source_name: "Report claim matrix",
              authority_tier: "report",
              freshness: "current report",
              artifact_type: "claim_chart",
              section: "claims",
              patent_id: "US-FTODemo-001",
              relevance: 0.92,
              provenance: [{ label: "Citation", value: "Claim 1 / column 12" }],
              follow_up_target: {
                target_type: "patent",
                target_id: "US-FTODemo-001",
                suggested_note:
                  "Counsel should confirm whether claim 1 reads on the launch candidate.",
              },
            },
          ],
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
          decision_counts: { accept: 1, reject: 0, edit: 1 },
          findings_total: 4,
          findings_reviewed: 2,
          completion_pct: 50,
        }),
      });
    },
  );

  await page.route(
    `**/api/v1/analyses/${ANALYSIS_ID}/decisions`,
    async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            id: "decision-e2e-1",
            finding_type: "patent",
            finding_ref: "US0000000001A1",
            decision: "reject",
            note: "Counsel override from e2e.",
            edited_text: "",
            reviewer_user_id: "usr-demo",
            reviewer_name: "Demo Counsel",
            reviewer_email: "counsel@example.test",
            created_at: "2026-04-24T10:04:00.000Z",
            updated_at: "2026-04-24T10:04:00.000Z",
          }),
        });
        return;
      }
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
    `**/api/v1/analyses/${ANALYSIS_ID}/review-handoff`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          comment_id: "comment-e2e-1",
          created_at: "2026-04-24T10:02:00.000Z",
          escalated_to_review: true,
          target_type: "analysis",
          target_id: ANALYSIS_ID,
          review_status: {
            analysis_id: ANALYSIS_ID,
            status: "under_review",
            note: "Evidence routed to counsel.",
            reviewer_name: "Demo Counsel",
            reviewer_email: "counsel@example.test",
            reviewed_at: null,
            updated_at: "2026-04-24T10:02:00.000Z",
            decision_counts: { accept: 1, reject: 0, edit: 1 },
            findings_total: 4,
            findings_reviewed: 2,
            completion_pct: 50,
          },
        }),
      });
    },
  );

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

  await page.route("**/api/v1/monitors", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "mon-e2e-1",
        compound_smiles: "OC(=O)CCC(O)=O",
        compound_name: "Succinic acid",
        source_analysis_id: ANALYSIS_ID,
        source_report_id: ANALYSIS_ID,
        source_trust_mode: "counsel",
        schedule: "weekly",
        is_active: true,
        jurisdiction_bundle: "global",
        target_jurisdictions: ["US", "EP"],
        strategy_version: "demo",
        monitoring_strategy: {},
        watch_targets: [],
        last_run_at: null,
        last_full_refresh_at: null,
        last_run_mode: null,
        last_run_status: null,
        last_run_summary: null,
        last_patent_count: 0,
        created_at: "2026-04-24T10:03:00.000Z",
      }),
    });
  });

  await page.route(`**/api/v1/reports/${ANALYSIS_ID}/share`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ share_token: "sg_demo_e2e_share" }),
    });
  });
}

test.describe("Flagship report workspace", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("praviar_welcomed", "true");
      window.localStorage.setItem("praviar_tour_complete", "true");
    });
    await mockFlagshipWorkspaceApis(page);
  });

  test("connects report tabs, evidence search, review, and watch while enforcing export and share gates", async ({
    page,
  }) => {
    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    await expect(page.getByText("Succinic acid").first()).toBeVisible({
      timeout: 15_000,
    });
    const handoffRail = page.getByTestId("report-evidence-handoff");
    await expect(handoffRail).toBeVisible();
    await expect(handoffRail).toContainText("Screening verdict");
    await expect(handoffRail).toContainText("3 blockers");
    await expect(handoffRail).toContainText("Material review");
    await expect(handoffRail).toContainText("4/5 sources");
    await expect(handoffRail).toContainText("Evidence coverage");
    await expect(handoffRail).toContainText("Source audit");
    await expect(handoffRail).toContainText("Data quality");
    await expect(handoffRail).toContainText("Counsel verify");
    await expect(handoffRail).toContainText("Reliance readiness");
    await expect(handoffRail).toContainText("Not ready for reliance");
    await expect(handoffRail).toContainText("Export blocked");
    await expect(handoffRail).toContainText("US, EP lanes block export");
    await expect(handoffRail).toContainText("Verify gaps");
    await expect(handoffRail).toContainText("Create review handoff");
    await expect(
      page.getByRole("button", { name: /Review findings/ }),
    ).toContainText("Ledger · 2/4");

    await handoffRail
      .getByRole("button", { name: "Create review handoff" })
      .click();
    await expect(handoffRail).toContainText("Review handoff created");
    await expect(page).toHaveURL(/tab=comments/);

    await page.getByRole("tab", { name: /Claims/ }).click();
    await expect(page).toHaveURL(/tab=claims/);
    await expect(
      page
        .getByRole("button", {
          name: /Claim 1: Partial.*Partially Met/iu,
        })
        .first(),
    ).toBeVisible();

    await page.getByRole("button", { name: "Open chat" }).click();
    await page.getByRole("tab", { name: "Evidence search" }).click();
    await expect(
      page.getByRole("heading", { name: "Governed evidence search" }),
    ).toBeVisible();
    await expect(
      page.getByRole("radio", { name: "Report-grounded" }),
    ).toBeVisible();

    await page
      .getByLabel("Evidence search query")
      .fill("succinate claim 1 blocking family");
    await page.getByRole("button", { name: "Search report evidence" }).click();
    await expect(
      page.getByText("Lead blocker claim 1 mapped to succinate salt coverage"),
    ).toBeVisible();
    await expect(page.getByText("Review handoff route")).toBeVisible();

    await page.getByRole("button", { name: "Send to review" }).first().click();
    await expect(
      page
        .getByRole("dialog", { name: "Chat with report" })
        .getByText("Review handoff created"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Close chat" }).click();
    await page.getByRole("button", { name: "Watch" }).click();
    await expect(page.getByRole("button", { name: "Watching" })).toBeVisible();

    await page
      .getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      })
      .click();
    await expect(
      page.getByTestId("report-export-recovery-ai-action"),
    ).toBeFocused();
    await expect(
      page.getByRole("dialog", { name: "Export evidence packet" }),
    ).toHaveCount(0);

    await page
      .getByRole("button", { name: /^Share$/ })
      .first()
      .click();
    await expect(page.getByText("Share governed report")).toBeVisible();
    await expect(page.getByText("No governed link retrieved")).toBeVisible();
    await expect(
      page.getByLabel("Share report identity").getByText(TEST_REPORT.report_id),
    ).toBeVisible();
    await expect(
      page.getByText("Export blocked: US, EP lanes block export.").first(),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Generate governed link" }),
    ).toBeDisabled();
  });

  test("opens directly into report tab state from URL params", async ({
    page,
  }) => {
    await page.goto(`/analyses/${ANALYSIS_ID}/report?tab=claims`);

    await expect(page.getByRole("tab", { name: /Claims/ })).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(
      page
        .getByRole("button", {
          name: /Claim 1: Partial.*Partially Met/iu,
        })
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Open chat" }).click();
    await page.getByRole("tab", { name: "Evidence search" }).click();
    await expect(
      page.getByRole("tab", { name: "Evidence search" }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(
      page.getByRole("heading", { name: "Governed evidence search" }),
    ).toBeVisible();
  });

  test("counsel next actions stays premium, governed, and overflow-safe", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    const panel = page.getByTestId("counsel-next-actions");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(panel).toContainText("Counsel next actions");
    await expect(panel).toContainText("AI-assisted triage");
    await expect(panel).toContainText("No legal conclusion changed");
    await expect(panel).toContainText("Evidence required");
    await expect(
      panel
        .getByRole("list", { name: "Counsel next action queue" })
        .getByRole("listitem"),
    ).toHaveCount(5);
    await expect(
      panel.getByRole("button", {
        name: "Open Design brief for US0000000001A1",
      }),
    ).toBeVisible();

    for (const viewport of [
      { width: 1280, height: 900 },
      { width: 768, height: 900 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await panel.scrollIntoViewIfNeeded();

      const metrics = await panel.evaluate((node) => {
        const panelRect = node.getBoundingClientRect();
        const controls = Array.from(
          node.querySelectorAll<HTMLElement>("button"),
        ).map((control) => {
          const rect = control.getBoundingClientRect();
          return {
            height: rect.height,
            left: rect.left,
            right: rect.right,
            width: rect.width,
          };
        });

        return {
          left: panelRect.left,
          right: panelRect.right,
          overflow:
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
          controls,
        };
      });

      expect(metrics.left).toBeGreaterThanOrEqual(-1);
      expect(metrics.right).toBeLessThanOrEqual(viewport.width + 1);
      expect(metrics.overflow).toBeLessThanOrEqual(1);
      for (const control of metrics.controls) {
        expect(control.height).toBeGreaterThanOrEqual(40);
        expect(control.width).toBeGreaterThanOrEqual(40);
        expect(control.left).toBeGreaterThanOrEqual(-1);
        expect(control.right).toBeLessThanOrEqual(viewport.width + 1);
      }
    }
  });

  test("mobile claims evidence is readable and proof-led at 320px", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto(`/analyses/${ANALYSIS_ID}/report?tab=claims`);

    const row = page.getByTestId("claim-element-row-1").first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row).toContainText("Met");
    await expect(row).toContainText("95%");
    await expect(
      page.getByTestId("claim-element-evidence-summary-1").first(),
    ).toContainText("C4 dicarboxylic acid");

    const textOverflow = await page
      .getByTestId("claim-element-text-1")
      .first()
      .evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(textOverflow).toBeLessThanOrEqual(1);

    const pageOverflow = await page.evaluate(
      () =>
        Math.max(
          document.body.scrollWidth,
          document.documentElement.scrollWidth,
        ) - window.innerWidth,
    );
    expect(pageOverflow).toBeLessThanOrEqual(1);

    await page
      .getByRole("button", {
        name: /view source for .* claim 1 element 1/i,
      })
      .first()
      .click();

    const drilldown = page.getByTestId("evidence-drilldown");
    await expect(drilldown).toBeVisible();
    await expect(drilldown).toContainText("Element Under Analysis");
    await expect(drilldown).toContainText("Analyst Evidence");
    await expect(
      page.getByTestId("evidence-drilldown-highlight"),
    ).toContainText("A method for producing a C4 dicarboxylic acid");

    const box = await drilldown.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
  });

  test("mobile report picker exposes every section without horizontal overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/analyses/${ANALYSIS_ID}/report?tab=meta`);

    const sectionPicker = page.getByRole("combobox", {
      name: "Report section",
    });
    await expect(sectionPicker).toBeVisible({ timeout: 15_000 });
    await expect(sectionPicker).toHaveValue("meta");
    await expect(page.getByTestId("report-evidence-handoff")).toContainText(
      "4/5 sources",
    );
    await expect(page.getByTestId("report-evidence-handoff")).toContainText(
      "Evidence coverage",
    );
    await expect(page.getByTestId("report-evidence-handoff")).toContainText(
      "Counsel verify",
    );
    await expect(page.getByTestId("report-evidence-handoff")).toContainText(
      "Reliance readiness",
    );
    await expect(page.getByTestId("report-evidence-handoff")).toContainText(
      "Not ready for reliance",
    );
    await expect(
      page.getByRole("toolbar", { name: /Report command bar for/u }),
    ).toBeVisible();
    const commandMetrics = await page
      .getByRole("toolbar", { name: /Report command bar for/u })
      .evaluate((toolbar) => {
        const toolbarRect = toolbar.getBoundingClientRect();
        const summary = toolbar.querySelector(
          "[data-praviar-mobile-command-summary]",
        );
        const summaryRect = summary?.getBoundingClientRect();
        const buttons = Array.from(toolbar.querySelectorAll("button")).map(
          (button) => {
            const rect = button.getBoundingClientRect();
            return {
              label:
                button.getAttribute("aria-label") ??
                button.textContent?.trim() ??
                "button",
              width: rect.width,
              height: rect.height,
            };
          },
        );

        return {
          height: toolbarRect.height,
          summaryHeight: summaryRect?.height ?? 0,
          buttons,
        };
      });
    expect(commandMetrics.height).toBeLessThanOrEqual(80);
    expect(commandMetrics.summaryHeight).toBe(0);
    for (const button of commandMetrics.buttons) {
      expect(button.height).toBeGreaterThanOrEqual(44);
      expect(button.width).toBeGreaterThanOrEqual(44);
    }

    await expect(
      page.getByRole("button", { name: "Review findings" }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("toolbar", { name: /Report command bar for/u })
        .getByRole("button", { name: "Search reviewed evidence" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "More report actions" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Open chat" })).toHaveCount(
      0,
    );

    await page.getByRole("button", { name: "More report actions" }).click();
    let actionsDialog = page.getByRole("dialog", { name: "Report actions" });
    await expect(actionsDialog).toBeVisible();
    await expect(
      actionsDialog.getByRole("group", {
        name: /Current report /u,
      }),
    ).toBeVisible();
    await actionsDialog
      .getByRole("button", { name: "Search reviewed evidence" })
      .click();
    await expect(
      page.getByPlaceholder("Search reviewed evidence"),
    ).toBeFocused();

    await page
      .getByRole("button", {
        name: "AI-assisted report evidence gap check",
      })
      .click();
    const chatDialog = page.getByRole("dialog", { name: "Chat with report" });
    await expect(chatDialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(chatDialog).toBeHidden();
    await expect(
      page.getByRole("button", {
        name: "AI-assisted report evidence gap check",
      }),
    ).toBeFocused();

    await page.getByRole("button", { name: "More report actions" }).click();
    actionsDialog = page.getByRole("dialog", { name: "Report actions" });
    await expect(actionsDialog).toBeVisible();
    const actionTargets = await actionsDialog.evaluate((dialog) =>
      Array.from(dialog.querySelectorAll("button")).map((button) => {
        const rect = button.getBoundingClientRect();
        return {
          label:
            button.getAttribute("aria-label") ??
            button.textContent?.trim() ??
            "button",
          width: rect.width,
          height: rect.height,
        };
      }),
    );
    for (const target of actionTargets) {
      expect(target.height).toBeGreaterThanOrEqual(44);
      expect(target.width).toBeGreaterThanOrEqual(44);
    }

    await expect(
      actionsDialog.getByRole("button", { name: "Search reviewed evidence" }),
    ).toBeVisible();
    await expect(
      actionsDialog.getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Share report" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Watch" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Print current section" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Flag for Review" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit feedback" }),
    ).toBeVisible();

    await actionsDialog
      .getByRole("button", {
        name: "Review export blockers before exporting evidence packet",
      })
      .click();
    await expect(actionsDialog).toBeHidden();
    await expect(
      page.getByTestId("report-export-recovery-ai-action"),
    ).toBeFocused();

    await expect(page.locator("[data-print-trigger]")).toHaveCount(0);

    const overflowBefore = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflowBefore).toBeLessThanOrEqual(1);

    await sectionPicker.selectOption("regulatory");

    await expect(page).toHaveURL(/tab=regulatory/);
    await expect(sectionPicker).toHaveValue("regulatory");
    await expect(
      page.getByPlaceholder("Search reviewed evidence"),
    ).toBeVisible();

    const overflowAfter = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflowAfter).toBeLessThanOrEqual(1);
  });

  test("keeps the report handoff rail inside the mobile viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    const handoffRail = page.getByTestId("report-evidence-handoff");
    await expect(handoffRail).toBeVisible({ timeout: 15_000 });

    const railBox = await handoffRail.boundingBox();
    const viewport = page.viewportSize();
    expect(railBox).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(railBox!.x).toBeGreaterThanOrEqual(-1);
    expect(railBox!.x + railBox!.width).toBeLessThanOrEqual(
      viewport!.width + 1,
    );

    const horizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(horizontalOverflow).toBeLessThanOrEqual(1);
  });

  test("reviewer decision panel opens canonical findings and restores focus", async ({
    page,
  }) => {
    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    const opener = page.getByTestId("reviewer-decision-button");
    await expect(opener).toBeVisible({ timeout: 15_000 });
    await opener.click();

    const dialog = page.getByRole("dialog", { name: "Review findings" });
    await expect(dialog).toBeVisible();
    await expect(
      page.getByTestId("reviewer-finding-US0000000001A1"),
    ).toBeVisible();
    await expect(
      page.getByTestId("reviewer-review-progress-US0000000001A1"),
    ).toHaveText("0/2 reviews");
    await expect(
      page.getByTestId("reviewer-decision-panel-close"),
    ).toBeFocused();

    await page.keyboard.press("Escape");

    await expect(dialog).toBeHidden();
    await expect(opener).toBeFocused();
  });

  test("blocked report access stays branded and mobile-safe", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.unroute(REPORT_ROUTE);
    await page.route(REPORT_ROUTE, async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Forbidden" }),
      });
    });

    await page.goto(`/analyses/${ANALYSIS_ID}/report`);

    await expect(
      page.getByRole("heading", { name: "Report access unavailable" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Team-scoped access")).toBeVisible();
    await expect(page.getByText("No report content exposed")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Export$/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Share$/ })).toHaveCount(0);

    const overflow = await page.evaluate(
      () =>
        Math.max(
          document.body.scrollWidth,
          document.documentElement.scrollWidth,
        ) - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
