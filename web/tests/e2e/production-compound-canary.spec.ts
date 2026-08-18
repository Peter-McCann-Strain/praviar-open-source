import { writeFile } from "node:fs/promises";
import type { APIResponse, Page, Response, Route } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import { parseProductionCompoundCanaryEnvironment } from "./fixtures/production-compound-canary-gate";
import { attachReleaseReportVisualReceipts } from "./fixtures/release-report-visual-gate";
import { classifyStagingAnalysisStatus } from "./fixtures/staging-journey-gate";

const production = parseProductionCompoundCanaryEnvironment(process.env);
const ANALYSIS_TERMINAL_TIMEOUT_MS = 12 * 60 * 1000;

function isApiPath(response: Response, suffix: string): boolean {
  return new URL(response.url()).pathname.endsWith(suffix);
}

function candidateApiURL(pathname: string): string {
  return new URL(pathname, production.candidateApiOrigin).toString();
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

  await page.getByLabel(/email address/i).fill(production.userEmail);
  await page.getByRole("button", { name: /^(continue|sign in)$/i }).click();
  await page.getByLabel(/password/i).fill(production.password);
  await page.getByRole("button", { name: /^(continue|sign in)$/i }).click();
  await expect(page).toHaveURL(/\/dashboard(?:[/?#]|$)/u, {
    timeout: 30_000,
  });
  await expect(
    page.getByRole("heading", { name: "Dashboard", exact: true }),
  ).toBeVisible();
}

async function currentAuthorizationHeaders(
  page: Page,
): Promise<Record<string, string>> {
  const token = await page.evaluate(async () => {
    const clerk = (
      window as Window & {
        Clerk?: { session?: { getToken?: () => Promise<string | null> } };
      }
    ).Clerk;
    return (await clerk?.session?.getToken?.()) ?? null;
  });
  expect(token, "Clerk production canary session token").toBeTruthy();
  if (!token)
    throw new Error("Production canary session token is unavailable.");
  return { Authorization: `Bearer ${token}` };
}

async function assertCandidateApiRelease(page: Page): Promise<void> {
  const response = await page.request.get(candidateApiURL("/api/health/ready"));
  await expectSuccessful(response, "candidate API readiness");
  const readiness = (await response.json()) as {
    status?: string;
    version?: string;
  };
  expect(readiness.status, "candidate API readiness status").toBe("ready");
  expect(readiness.version, "candidate API release version").toBe(
    production.releaseGitSha,
  );
}

async function proxyRouteToCandidate(
  route: Route,
  routedCriticalPaths: Set<string>,
): Promise<void> {
  const request = route.request();
  const source = new URL(request.url());
  const normalApiOrigin = new URL(production.apiProbeURL).origin;
  expect(source.origin, "intercepted normal API origin").toBe(normalApiOrigin);
  const target = new URL(
    `${source.pathname}${source.search}`,
    production.candidateApiOrigin,
  );
  if (
    (request.method() === "POST" && source.pathname === "/api/v1/analyses") ||
    (request.method() === "GET" &&
      /^\/api\/v1\/reports\/[^/]+$/u.test(source.pathname))
  ) {
    routedCriticalPaths.add(`${request.method()} ${source.pathname}`);
  }
  const response = await route.fetch({ url: target.toString() });
  await route.fulfill({ response });
}

async function installCandidateApiRouting(page: Page): Promise<Set<string>> {
  await assertCandidateApiRelease(page);
  const routedCriticalPaths = new Set<string>();
  const normalApiOrigin = new URL(production.apiProbeURL).origin;
  await page.route(`${normalApiOrigin}/**`, (route) =>
    proxyRouteToCandidate(route, routedCriticalPaths),
  );
  return routedCriticalPaths;
}

async function waitForCompletedAnalysis(
  page: Page,
  analysisId: string,
): Promise<void> {
  const analysisUrl = new URL(
    `/api/v1/analyses/${analysisId}`,
    production.candidateApiOrigin,
  ).toString();
  const deadline = Date.now() + ANALYSIS_TERMINAL_TIMEOUT_MS;
  let lastStatus = "unavailable";
  let delayMs = 1_000;

  while (Date.now() < deadline) {
    const response = await page.request.get(analysisUrl, {
      headers: await currentAuthorizationHeaders(page),
    });
    await expectSuccessful(response, "production canary analysis status");
    const analysis = (await response.json()) as {
      id?: string;
      status?: string;
    };
    expect(analysis.id, "polled production analysis identity").toBe(analysisId);
    lastStatus =
      typeof analysis.status === "string" ? analysis.status : "invalid";
    if (classifyStagingAnalysisStatus(lastStatus) === "complete") return;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    delayMs = Math.min(delayMs * 2, 10_000);
  }
  throw new Error(
    `Production canary analysis did not complete before the release deadline; last status ${lastStatus}.`,
  );
}

test("authenticated cheap compound traverses the durable production report path", async ({
  page,
}, testInfo) => {
  test.setTimeout(16 * 60 * 1000);
  let cleanupUrl: string | null = null;
  let completed = false;
  let launchedAt: string | null = null;
  const routedCriticalPaths = await installCandidateApiRouting(page);

  try {
    await signIn(page);
    await page.goto("/analyses/new");
    await expect(page).toHaveURL(/\/analyses\/new(?:[/?#]|$)/u);
    await page.getByLabel("Compound input").fill(production.launchCompound);
    await page.getByRole("button", { name: /Next: Configure/i }).click();
    await page.getByRole("button", { name: /Next: Review/i }).click();

    const launchResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        isApiPath(response, "/api/v1/analyses"),
    );
    launchedAt = new Date().toISOString();
    await page.getByRole("button", { name: "Start Analysis" }).click();
    const launchResponse = await launchResponsePromise;
    await expectSuccessful(launchResponse, "production analysis launch");
    const launched = (await launchResponse.json()) as { id?: string };
    expect(launched.id, "production analysis launch response id").toBeTruthy();
    if (!launched.id) {
      throw new Error("Production canary analysis id is unavailable.");
    }
    cleanupUrl = new URL(
      `/api/v1/analyses/${launched.id}`,
      production.candidateApiOrigin,
    ).toString();

    await waitForCompletedAnalysis(page, launched.id);
    const reportUrl = new URL(
      `/api/v1/reports/${launched.id}`,
      production.candidateApiOrigin,
    ).toString();
    const reportResponse = await page.request.get(reportUrl, {
      headers: await currentAuthorizationHeaders(page),
    });
    await expectSuccessful(reportResponse, "production canary report");
    const report = (await reportResponse.json()) as {
      generated_at?: string;
      report_id?: string;
    };
    expect(report.report_id, "production canary report id").toBeTruthy();
    expect(
      report.generated_at,
      "production canary report generation time",
    ).toBeTruthy();

    await page.goto(`/analyses/${launched.id}/report`);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(
      page
        .getByRole("button", {
          name: /Verify export readiness|Review export blockers/i,
        })
        .first(),
    ).toBeVisible();
    expect(
      [...routedCriticalPaths].some((entry) =>
        entry.startsWith("POST /api/v1/analyses"),
      ),
      "analysis launch must be proxied to the candidate API origin",
    ).toBe(true);
    expect(
      [...routedCriticalPaths].some((entry) =>
        entry.startsWith("GET /api/v1/reports/"),
      ),
      "rendered report must load from the candidate API origin",
    ).toBe(true);
    await assertCandidateApiRelease(page);
    await attachReleaseReportVisualReceipts({
      attachmentPrefix: "production-canary-report",
      page,
      testInfo,
    });

    const receipt = {
      analysis_id: launched.id,
      api_release_version: production.releaseGitSha,
      completed_at: new Date().toISOString(),
      compound: production.launchCompound,
      generated_at: report.generated_at,
      launched_at: launchedAt,
      release_git_sha: production.releaseGitSha,
      report_id: report.report_id,
      schema_version: 1,
      status: "completed",
    };
    await writeFile(
      testInfo.outputPath("production-compound-canary-receipt.json"),
      `${JSON.stringify(receipt, null, 2)}\n`,
      "utf8",
    );
    await testInfo.attach("production-compound-canary-receipt", {
      body: JSON.stringify(receipt, null, 2),
      contentType: "application/json",
    });
    completed = true;
  } finally {
    if (cleanupUrl) {
      const response = await page.request.delete(cleanupUrl, {
        headers: await currentAuthorizationHeaders(page),
      });
      expect(response.status(), "production canary cleanup status").toBe(204);
      const hidden = await page.request.get(cleanupUrl, {
        headers: await currentAuthorizationHeaders(page),
      });
      expect(hidden.status(), "deleted production canary must be hidden").toBe(
        404,
      );
    }
  }

  expect(completed, "production compound canary completion receipt").toBe(true);
});
