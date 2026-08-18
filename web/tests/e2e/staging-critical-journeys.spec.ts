import type { APIResponse, Page, Response } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import {
  classifyStagingAnalysisStatus,
  createCriticalJourneyLedger,
  parseStagingJourneyEnvironment,
} from "./fixtures/staging-journey-gate";
import { attachReleaseReportVisualReceipts } from "./fixtures/release-report-visual-gate";

const staging = parseStagingJourneyEnvironment(process.env);
const ANALYSIS_TERMINAL_TIMEOUT_MS = 12 * 60 * 1000;

function isApiPath(response: Response, suffix: string): boolean {
  return new URL(response.url()).pathname.endsWith(suffix);
}

async function expectSuccessful(
  response: Response | APIResponse,
  action: string,
) {
  expect(response.ok(), `${action} returned ${response.status()}`).toBe(true);
}

async function signIn(page: Page) {
  const response = await page.goto("/sign-in?return_to=%2Fdashboard", {
    waitUntil: "domcontentloaded",
  });
  expect(response, "sign-in navigation response").not.toBeNull();
  if (response) await expectSuccessful(response, "sign-in navigation");

  await page.getByLabel(/email address/i).fill(staging.userEmail);
  await page.getByRole("button", { name: /^(continue|sign in)$/i }).click();
  await page.getByLabel(/password/i).fill(staging.password);
  await page.getByRole("button", { name: /^(continue|sign in)$/i }).click();
  await expect(page).toHaveURL(/\/dashboard(?:[/?#]|$)/u, { timeout: 30_000 });
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
}

async function getClerkSessionToken(page: Page): Promise<string> {
  const token = await page.evaluate(async () => {
    const clerk = (
      window as Window & {
        Clerk?: { session?: { getToken?: () => Promise<string | null> } };
      }
    ).Clerk;
    return (await clerk?.session?.getToken?.()) ?? null;
  });
  expect(token, "Clerk staging session token").toBeTruthy();
  if (!token) throw new Error("Clerk staging session token is unavailable.");
  return token;
}

async function currentAuthorizationHeaders(
  page: Page,
): Promise<{ Authorization: string }> {
  return { Authorization: `Bearer ${await getClerkSessionToken(page)}` };
}

async function waitForCompletedAnalysis(
  page: Page,
  analysisId: string,
): Promise<void> {
  const analysisUrl = new URL(
    `/api/v1/analyses/${analysisId}`,
    staging.baseURL,
  ).toString();
  const deadline = Date.now() + ANALYSIS_TERMINAL_TIMEOUT_MS;
  let lastStatus = "unavailable";
  let delayMs = 1_000;

  while (Date.now() < deadline) {
    const response = await page.request.get(analysisUrl, {
      headers: await currentAuthorizationHeaders(page),
    });
    await expectSuccessful(response, "newly launched analysis status");
    const analysis = (await response.json()) as {
      id?: string;
      status?: string;
    };
    expect(analysis.id, "polled analysis identity").toBe(analysisId);
    lastStatus =
      typeof analysis.status === "string" ? analysis.status : "invalid";

    if (classifyStagingAnalysisStatus(lastStatus) === "complete") return;

    await new Promise((resolve) => setTimeout(resolve, delayMs));
    delayMs = Math.min(delayMs * 2, 10_000);
  }

  throw new Error(
    `Newly launched analysis did not complete before the release-gate deadline; last status ${lastStatus}.`,
  );
}

test("authenticated staging release journey executes every critical action", async ({
  page,
}, testInfo) => {
  test.setTimeout(18 * 60 * 1000);
  const ledger = createCriticalJourneyLedger();

  await signIn(page);
  ledger.mark("sign_in");

  const setupResponsePromise = page.waitForResponse((response) =>
    isApiPath(response, "/api/v1/setup-readiness"),
  );
  await page.reload({ waitUntil: "domcontentloaded" });
  await expectSuccessful(await setupResponsePromise, "setup readiness");
  const setupRegion = page.getByRole("region", {
    name: "Workspace launch checklist",
  });
  await expect(setupRegion).toBeVisible();
  await expect(
    setupRegion.getByRole("progressbar", { name: "Workspace setup readiness" }),
  ).toBeVisible();
  const setupDisclosure = setupRegion.getByText(
    "Review setup evidence and recovery actions",
  );
  await expect(setupDisclosure).toBeVisible();
  await setupDisclosure.click();
  const startAnalysisRecovery = setupRegion.getByRole("link", {
    name: /Start an analysis/i,
  });
  await expect(startAnalysisRecovery).toHaveAttribute("href", "/analyses/new");
  await startAnalysisRecovery.click();
  await expect(page).toHaveURL(/\/analyses\/new(?:[/?#]|$)/u);
  ledger.mark("setup_readiness_loaded");

  const callbackResponse = await page.goto(
    "/sign-in/sso-callback?return_to=%2Fdashboard",
    { waitUntil: "domcontentloaded" },
  );
  expect(callbackResponse, "SSO callback navigation response").not.toBeNull();
  if (callbackResponse)
    await expectSuccessful(callbackResponse, "SSO callback");
  await expect(page).toHaveURL(/\/dashboard(?:[/?#]|$)/u, { timeout: 30_000 });
  ledger.mark("sso_callback_route");

  let checkoutSuccessUrl: string | null = null;
  page.on("request", (request) => {
    if (
      request.method() !== "POST" ||
      !new URL(request.url()).pathname.endsWith(
        "/api/v1/billing/credit-packs/checkout",
      )
    ) {
      return;
    }
    const payload = request.postDataJSON() as {
      cancel_url?: string;
      credit_pack_id?: string;
      success_url?: string;
    };
    expect(payload.credit_pack_id).toBeTruthy();
    expect(payload.success_url).toContain("checkout=success");
    expect(payload.cancel_url).toContain("checkout=cancelled");
    checkoutSuccessUrl = payload.success_url ?? null;
  });
  await page.route("https://checkout.stripe.com/**", async (route) => {
    expect(checkoutSuccessUrl, "checkout success return URL").toBeTruthy();
    await route.fulfill({
      status: 302,
      headers: {
        location: new URL(
          checkoutSuccessUrl ?? "/billing",
          staging.baseURL,
        ).toString(),
      },
    });
  });

  await page.goto("/billing");
  await expect(
    page.getByRole("heading", { name: "Credits & Billing" }),
  ).toBeVisible();
  const reconciliationResponses = new Set<string>();
  page.on("response", (response) => {
    const pathname = new URL(response.url()).pathname;
    for (const suffix of [
      "/api/v1/billing/status",
      "/api/v1/billing/usage",
      "/api/v1/billing/invoices",
    ]) {
      if (pathname.endsWith(suffix) && response.ok()) {
        reconciliationResponses.add(suffix);
      }
    }
  });
  const checkoutResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      isApiPath(response, "/api/v1/billing/credit-packs/checkout"),
  );
  await page
    .getByRole("button", { name: /^Quick buy .+ for \$/i })
    .first()
    .click();
  const checkoutResponse = await checkoutResponsePromise;
  await expectSuccessful(checkoutResponse, "backend checkout creation");
  const checkout = (await checkoutResponse.json()) as {
    checkout_url?: string;
    session_id?: string;
  };
  if (process.env.GITHUB_ACTIONS === "true" && checkout.session_id) {
    process.stdout.write(`::add-mask::${checkout.session_id}\n`);
  }
  expect(checkout.session_id, "Stripe test Checkout session id").toMatch(
    /^cs_test_/u,
  );
  expect(new URL(checkout.checkout_url ?? "").hostname).toBe(
    "checkout.stripe.com",
  );
  ledger.mark("billing_backend_checkout_created");
  await expect(page.getByText("Report Credit checkout returned")).toBeVisible();
  await expect
    .poll(() => reconciliationResponses.size, {
      message:
        "all three billing ledger surfaces refetched after checkout return",
    })
    .toBe(3);
  ledger.mark("billing_simulated_return_reconciled");

  let analysisCleanupUrl: string | null = null;
  let exportCleanupUrl: string | null = null;
  let shareCleanupUrl: string | null = null;
  try {
    await page.goto("/analyses/new");
    await expect(page).toHaveURL(/\/analyses\/new(?:[/?#]|$)/u);
    await page.getByLabel("Compound input").fill(staging.launchCompound);
    await page.getByRole("button", { name: /Next: Configure/i }).click();
    await page.getByRole("button", { name: /Next: Review/i }).click();
    const launchResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        isApiPath(response, "/api/v1/analyses"),
    );
    await page.getByRole("button", { name: "Start Analysis" }).click();
    const launchResponse = await launchResponsePromise;
    await expectSuccessful(launchResponse, "analysis launch");
    const launched = (await launchResponse.json()) as { id?: string };
    expect(launched.id, "analysis launch response id").toBeTruthy();
    if (!launched.id)
      throw new Error("Analysis launch response id is unavailable.");
    analysisCleanupUrl = new URL(
      `/api/v1/analyses/${launched.id}`,
      launchResponse.url(),
    ).toString();
    await expect(page).toHaveURL(
      new RegExp(`/analyses/${launched.id}(?:[/?#]|$)`),
    );
    ledger.mark("analysis_launch");

    await waitForCompletedAnalysis(page, launched.id);
    ledger.mark("analysis_terminal_completed");

    const reportResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        isApiPath(response, `/api/v1/reports/${launched.id}`),
    );
    await page.goto(`/analyses/${launched.id}/report`);
    const reportResponse = await reportResponsePromise;
    await expectSuccessful(reportResponse, "newly launched analysis report");
    const launchedReport = (await reportResponse.json()) as {
      generated_at?: string;
      report_id?: string;
    };
    expect(
      launchedReport.report_id,
      "newly launched analysis report identifier",
    ).toBeTruthy();
    expect(
      launchedReport.generated_at,
      "newly launched analysis report generation time",
    ).toBeTruthy();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(
      page
        .getByRole("button", {
          name: /Verify export readiness|Review export blockers/i,
        })
        .first(),
    ).toBeVisible();
    ledger.mark("launched_report_open");
    await attachReleaseReportVisualReceipts({
      attachmentNames: {
        desktop: "launched-report-desktop",
        mobile: "launched-report-mobile",
      },
      attachmentPrefix: "launched-report",
      page,
      testInfo,
    });
    ledger.mark("launched_report_visual_receipts");

    const blockedExportResponse = await page.request.post(
      new URL(
        `/api/v1/reports/${launched.id}/export`,
        launchResponse.url(),
      ).toString(),
      {
        headers: await currentAuthorizationHeaders(page),
        data: {
          format: "pdf",
          sections: [],
          audience: "full",
        },
      },
    );
    expect(
      blockedExportResponse.status(),
      "export must fail closed before persisted legal approval",
    ).toBe(409);
    await page
      .getByRole("button", {
        name: /Verify export readiness|Review export blockers/i,
      })
      .first()
      .click();
    await expect(page.getByTestId("report-reliance-readiness")).toBeVisible();
    ledger.mark("export_blocked_before_review");

    await page.getByTestId("reviewer-decision-button").click();
    const reviewerPanel = page.getByTestId("reviewer-decision-panel");
    await expect(reviewerPanel).toBeVisible();
    const reviewableFindings = reviewerPanel.locator(
      "[data-reviewer-finding-ref]",
    );
    const reviewableFindingCount = await reviewableFindings.count();
    expect(
      reviewableFindingCount,
      "staging journey must exercise at least one governed finding decision",
    ).toBeGreaterThan(0);
    for (let index = 0; index < reviewableFindingCount; index += 1) {
      const finding = reviewableFindings.nth(index);
      await finding.getByRole("radio", { name: "accept" }).click();
      await finding
        .getByLabel(/Decision (?:rationale|note)/i)
        .fill(
          "Staging release gate reviewed the cited source spans, claim mapping, jurisdiction, legal-status snapshot, and evidence caveats for this finding.",
        );
      const decisionResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          isApiPath(response, `/api/v1/analyses/${launched.id}/decisions`),
      );
      await finding.getByRole("button", { name: "Save my decision" }).click();
      await expectSuccessful(
        await decisionResponsePromise,
        `reviewer finding decision ${index + 1}`,
      );
      await expect(
        finding.getByTestId("reviewer-finding-existing"),
      ).toBeVisible();
    }
    await reviewerPanel
      .getByRole("button", { name: "Close reviewer panel" })
      .click();
    await expect(reviewerPanel).toBeHidden();
    ledger.mark("reviewer_findings_decided");

    const lifecycle = page.getByTestId("report-review-lifecycle-control");
    await lifecycle.scrollIntoViewIfNeeded();
    await expect(lifecycle).toBeVisible();
    await lifecycle.getByRole("radio", { name: "Approved" }).click();
    await lifecycle
      .getByLabel("Audit note")
      .fill(
        "Staging release gate accepted every material finding and verified the signed evidence, jurisdiction, citation, and export-readiness controls.",
      );
    const approvalResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        isApiPath(response, `/api/v1/analyses/${launched.id}/review-status`),
    );
    await lifecycle.getByRole("button", { name: "Record approved" }).click();
    await expectSuccessful(
      await approvalResponsePromise,
      "persisted counsel approval",
    );
    await expect(
      lifecycle.getByText("Approved recorded in the governed review ledger."),
    ).toBeVisible();
    ledger.mark("report_review_approved");

    await expect(
      page
        .getByRole("button", {
          name: /Export evidence packet|Prepare evidence packet export with source caveat/i,
        })
        .first(),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: /Export evidence packet|Prepare evidence packet export with source caveat/i,
      })
      .first()
      .click();
    const exportDialog = page.getByRole("dialog", {
      name: "Export evidence packet",
    });
    await expect(exportDialog).toBeVisible();
    const exportStartPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        isApiPath(response, `/api/v1/reports/${launched.id}/export`),
    );
    await exportDialog.getByRole("button", { name: "Export packet" }).click();
    const exportStartResponse = await exportStartPromise;
    await expectSuccessful(exportStartResponse, "export start");
    const exportJob = (await exportStartResponse.json()) as { job_id?: string };
    expect(exportJob.job_id, "export response job id").toBeTruthy();
    if (!exportJob.job_id)
      throw new Error("Export response job id is unavailable.");
    exportCleanupUrl = new URL(
      `/api/v1/exports/${exportJob.job_id}`,
      exportStartResponse.url(),
    ).toString();
    await expect(exportDialog.getByText("Evidence packet ready")).toBeVisible({
      timeout: 120_000,
    });
    ledger.mark("export_complete");
    const downloadPromise = page.waitForEvent("download");
    await exportDialog
      .getByRole("link", {
        name: /download (?:verified packet|verified claim-chart DOCX)|Export ready/i,
      })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBeTruthy();
    ledger.mark("export_download");
    await exportDialog
      .getByRole("button", { name: "Close export dialog" })
      .click();

    await page
      .getByRole("button", { name: /^Share$/ })
      .first()
      .click();
    const shareDialog = page.getByRole("dialog", {
      name: "Share governed report",
    });
    await expect(shareDialog).toBeVisible();
    const launchedAnalysisResponse = await page.request.get(
      new URL(`/api/v1/analyses/${launched.id}`, staging.baseURL).toString(),
      { headers: await currentAuthorizationHeaders(page) },
    );
    await expectSuccessful(
      launchedAnalysisResponse,
      "newly launched analysis share state check",
    );
    const launchedAnalysis = (await launchedAnalysisResponse.json()) as {
      share_active?: boolean;
    };
    expect(
      launchedAnalysis.share_active,
      "the newly launched report must begin without an active share",
    ).toBe(false);
    const shareResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        isApiPath(response, `/api/v1/reports/${launched.id}/share`),
    );
    await shareDialog
      .getByLabel("Recipient email")
      .fill(staging.shareRecipientEmail);
    await shareDialog
      .getByRole("button", { name: "Send verification invitation" })
      .click();
    const shareResponse = await shareResponsePromise;
    await expectSuccessful(shareResponse, "share creation");
    const share = (await shareResponse.json()) as {
      id?: string;
      share_token?: string;
    };
    expect(share.id, "recipient grant id").toBeTruthy();
    expect(share.share_token, "share response token").toBeTruthy();
    if (!share.id || !share.share_token) {
      throw new Error("Recipient grant response is incomplete.");
    }
    shareCleanupUrl = new URL(
      `/api/v1/reports/${launched.id}/share/${share.id}`,
      launchedAnalysisResponse.url(),
    ).toString();
    if (process.env.GITHUB_ACTIONS === "true") {
      process.stdout.write(`::add-mask::${share.share_token}\n`);
    }
    ledger.mark("recipient_grant_create");

    await page.goto(`/share/${share.share_token}`);
    await expect(
      page.getByRole("heading", { name: "Verify intended recipient" }),
    ).toBeVisible();
    await expect(page.getByText(staging.shareRecipientEmail)).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Send verification code" }),
    ).toBeVisible();
    ledger.mark("recipient_verification_gate_open");

    const flagResponse = await page.request.post(
      new URL(
        `/api/v1/analyses/${launched.id}/flag`,
        launchResponse.url(),
      ).toString(),
      { headers: await currentAuthorizationHeaders(page) },
    );
    await expectSuccessful(flagResponse, "review flag");
    await page.goto("/analyses");
    await expect(
      page.getByText(staging.launchCompound, { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByText("Review flagged", { exact: true }).first(),
    ).toBeVisible();
    ledger.mark("review_flag");
  } finally {
    const cleanupFailures: string[] = [];
    const clean = async (label: string, action: () => Promise<void>) => {
      try {
        await action();
      } catch (error) {
        cleanupFailures.push(
          `${label}: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    };
    if (shareCleanupUrl) {
      const cleanupUrl = shareCleanupUrl;
      await clean("share cleanup", async () => {
        const response = await page.request.delete(cleanupUrl, {
          headers: await currentAuthorizationHeaders(page),
        });
        await expectSuccessful(response, "share cleanup");
        ledger.mark("recipient_grant_revoke_cleanup");
      });
    }
    if (exportCleanupUrl) {
      const cleanupUrl = exportCleanupUrl;
      await clean("export cleanup", async () => {
        const response = await page.request.delete(cleanupUrl, {
          headers: await currentAuthorizationHeaders(page),
        });
        expect(response.status(), "export cleanup status").toBe(204);
        ledger.mark("export_cleanup");
      });
    }
    if (analysisCleanupUrl) {
      const cleanupUrl = analysisCleanupUrl;
      await clean("analysis cleanup", async () => {
        for (let attempt = 1; attempt <= 2; attempt += 1) {
          const response = await page.request.delete(cleanupUrl, {
            headers: await currentAuthorizationHeaders(page),
          });
          expect(
            response.status(),
            `analysis cleanup status (pass ${attempt})`,
          ).toBe(204);
        }
        const hidden = await page.request.get(cleanupUrl, {
          headers: await currentAuthorizationHeaders(page),
        });
        expect(hidden.status(), "deleted analysis must be hidden").toBe(404);
        ledger.mark("analysis_cleanup");
      });
    }
    expect(cleanupFailures, "critical journey cleanup failures").toEqual([]);
  }

  ledger.assertComplete();
  await testInfo.attach("critical-journey-receipt", {
    body: JSON.stringify({ actions: ledger.snapshot() }, null, 2),
    contentType: "application/json",
  });
});
