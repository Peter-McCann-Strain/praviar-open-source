import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { Response } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";

const LIVE_DATABASE_ENABLED = process.env.PLAYWRIGHT_LIVE_DATABASE === "true";
const LIVE_API_ORIGIN = new URL(
  process.env.NEXT_PUBLIC_API_URL ??
    `http://localhost:${Number(process.env.PLAYWRIGHT_API_PORT ?? 18_080)}`,
).origin;
const LIVE_DATABASE_RECEIPT_PATH = resolve(
  process.cwd(),
  process.env.PLAYWRIGHT_LIVE_DATABASE_RECEIPT_PATH ??
    "test-results/live-database/browser-credential-lifecycle.json",
);

function isLiveApiResponse(
  response: Response,
  method: string,
  path: string,
  status: number,
): boolean {
  const url = new URL(response.url());
  return (
    url.origin === LIVE_API_ORIGIN &&
    url.pathname === path &&
    response.request().method() === method &&
    response.status() === status &&
    !response.fromServiceWorker()
  );
}

type AnalysisListItem = {
  id: string;
  compound_name: string;
  status: string;
};

type AnalysisListResponse = {
  items: AnalysisListItem[];
  total: number;
};

type ReportResponse = {
  compound: {
    name: string;
  };
};

type CompoundListItem = {
  id: string;
  canonical_smiles: string;
  inchi_key: string;
  name: string;
  molecular_formula: string;
  molecular_weight: number | null;
  functional_groups: string[];
  pubchem_cid: number | null;
  first_analyzed_at: string;
  analysis_count: number;
};

type CompoundListResponse = {
  items: CompoundListItem[];
  total: number;
  page: number;
  per_page: number;
};

type PatentListItem = {
  id: string;
  patent_number: string;
  title: string;
  assignee: string;
  risk_level: string;
  cpc_codes: string[];
  expiry_date: string | null;
  analysis_id: string;
  compound_name: string;
};

type PatentListResponse = {
  items: PatentListItem[];
  total: number;
  page: number;
  per_page: number;
};

type PatentDetailResponse = {
  patent_analysis: {
    patent_id: string;
    title: string;
    assignee: string;
  };
  analysis_id: string;
};

type ReviewQueueListItem = {
  id: string;
  analysis_id: string;
  compound_name: string;
  analysis_status: string;
  body: string;
  assigned_to: string | null;
};

type ReviewQueueListResponse = {
  counts: {
    open_total: number;
    unassigned: number;
  };
  items: ReviewQueueListItem[];
};

type MonitorListItem = {
  id: string;
  compound_name: string;
  source_analysis_id: string;
};

type MonitorListResponse = {
  items: MonitorListItem[];
  total: number;
};

type APIKeyListItem = {
  id: string;
  name: string;
  revoked: boolean;
};

type APIKeyListResponse = {
  items: APIKeyListItem[];
  total: number;
};

type APIKeyCreatedResponse = {
  id: string;
  name: string;
  secret_key: string;
};

type APIKeyRevokedResponse = {
  status: string;
};

const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;

// The API-key journey receives a one-time credential. Network traces retain
// response bodies, so this suite relies on HTML results and secret-redacted
// screenshots instead of persisting trace archives.
test.use({ trace: "off" });

test.describe("live PostgreSQL-backed surfaces", () => {
  test.beforeAll(() => {
    if (LIVE_DATABASE_ENABLED) {
      rmSync(LIVE_DATABASE_RECEIPT_PATH, { force: true });
    }
  });

  test.skip(
    !LIVE_DATABASE_ENABLED,
    "Set PLAYWRIGHT_LIVE_DATABASE=true with the seeded local API running.",
  );

  test("analysis library and report render the records returned by the live API", async ({
    page,
  }) => {
    const listResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/analyses", 200);
    });

    await page.goto("/analyses");
    const listResponse = await listResponsePromise;
    const list = (await listResponse.json()) as AnalysisListResponse;

    expect(list.total, "seeded PostgreSQL analysis count").toBeGreaterThan(0);
    expect(
      list.items.length,
      "visible PostgreSQL analysis records",
    ).toBeGreaterThan(0);

    for (const analysis of list.items) {
      await expect(
        page.getByText(analysis.compound_name, { exact: true }).first(),
        `${analysis.compound_name} from the live list response`,
      ).toBeVisible();
    }

    const completedAnalyses = list.items.filter(
      (analysis) => analysis.status === "completed",
    );
    expect(
      completedAnalyses.length,
      "at least one completed seeded analysis",
    ).toBeGreaterThan(0);
    const completed = completedAnalyses[0];
    if (!completed) return;

    const detailResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(
        response,
        "GET",
        `/api/v1/analyses/${completed.id}`,
        200,
      );
    });
    await page.goto(`/analyses/${completed.id}`);
    const detailResponse = await detailResponsePromise;
    const detail = (await detailResponse.json()) as AnalysisListItem;
    expect(detail.id).toBe(completed.id);
    expect(detail.compound_name).toBe(completed.compound_name);
    await expect(
      page.getByText(completed.compound_name, { exact: true }).first(),
    ).toBeVisible();

    for (const completedAnalysis of completedAnalyses) {
      const reportResponsePromise = page.waitForResponse((response) => {
        return isLiveApiResponse(
          response,
          "GET",
          `/api/v1/reports/${completedAnalysis.id}`,
          200,
        );
      });
      await page.goto(`/analyses/${completedAnalysis.id}/report`);
      const reportResponse = await reportResponsePromise;
      const report = (await reportResponse.json()) as ReportResponse;
      expect(report.compound.name.toLocaleLowerCase()).toBe(
        completedAnalysis.compound_name.toLocaleLowerCase(),
      );
      await expect(page.getByRole("main")).toBeVisible();
      await expect(
        page.getByRole("heading", {
          name: report.compound.name,
          exact: true,
          level: 1,
        }),
      ).toBeVisible();
    }
  });

  test("monitor workspace renders live monitor-to-analysis provenance", async ({
    page,
  }) => {
    const monitorResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/monitors", 200);
    });

    await page.goto("/monitors");
    const monitorResponse = await monitorResponsePromise;
    const monitors = (await monitorResponse.json()) as MonitorListResponse;

    expect(monitors.total, "seeded PostgreSQL monitor count").toBeGreaterThan(
      0,
    );
    const analysisResponse = await page.request.get(
      `${LIVE_API_ORIGIN}/api/v1/analyses`,
      { headers: { Authorization: "Bearer dev-token" } },
    );
    expect(analysisResponse.status()).toBe(200);
    const analyses = (await analysisResponse.json()) as AnalysisListResponse;
    const analysisIds = new Set(analyses.items.map((analysis) => analysis.id));
    for (const monitor of monitors.items) {
      expect(monitor.source_analysis_id).toBeTruthy();
      expect(
        analysisIds.has(monitor.source_analysis_id),
        `${monitor.compound_name} monitor source is an authoritative analysis`,
      ).toBe(true);
      await expect(
        page.getByText(monitor.compound_name, { exact: true }).first(),
        `${monitor.compound_name} from the live monitor response`,
      ).toBeVisible();
    }
  });

  test("compound library renders live normalized identities and API-bound dossiers", async ({
    page,
  }) => {
    const listResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/compounds", 200);
    });

    await page.goto("/compounds");
    const listResponse = await listResponsePromise;
    const compounds = (await listResponse.json()) as CompoundListResponse;

    expect(compounds.total, "seeded PostgreSQL compound count").toBeGreaterThan(
      0,
    );
    expect(compounds.items.length, "visible normalized compounds").toBe(
      compounds.total,
    );
    expect(new Set(compounds.items.map((compound) => compound.id)).size).toBe(
      compounds.items.length,
    );

    for (const compound of compounds.items) {
      expect(compound.id).toMatch(UUID_V4_PATTERN);
      expect(compound.canonical_smiles).toBeTruthy();
      expect(compound.inchi_key).toBeTruthy();
      expect(compound.molecular_formula).toBeTruthy();
      expect(compound.analysis_count).toBeGreaterThan(0);

      const detailResponse = await page.request.get(
        `${LIVE_API_ORIGIN}/api/v1/compounds/${compound.id}`,
        { headers: { Authorization: "Bearer dev-token" } },
      );
      expect(detailResponse.status()).toBe(200);
      const authoritativeDetail =
        (await detailResponse.json()) as CompoundListItem;
      expect(authoritativeDetail).toEqual(compound);

      const toggle = page.getByRole("button", {
        name: `Show details for ${compound.name}`,
        exact: true,
      });
      await expect(toggle).toBeVisible();
      await toggle.click();

      const dossier = page.locator(`[id="compound-detail-${compound.id}"]`);
      await expect(dossier).toBeVisible();
      await expect(
        dossier.getByRole("heading", {
          name: authoritativeDetail.name,
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        dossier.getByText(authoritativeDetail.canonical_smiles, {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        dossier.getByText(authoritativeDetail.inchi_key, { exact: true }),
      ).toBeVisible();
      await expect(
        dossier.getByText(authoritativeDetail.molecular_formula, {
          exact: true,
        }),
      ).toBeVisible();
      if (authoritativeDetail.pubchem_cid !== null) {
        const pubchemLink = dossier.getByRole("link", {
          name: new RegExp(
            `^Open PubChem CID ${authoritativeDetail.pubchem_cid} `,
            "u",
          ),
        });
        await expect(pubchemLink).toHaveAttribute(
          "href",
          `https://pubchem.ncbi.nlm.nih.gov/compound/${authoritativeDetail.pubchem_cid}`,
        );
      }
    }
  });

  test("patent library renders publishable PostgreSQL evidence with report provenance", async ({
    page,
  }) => {
    const listResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/patents", 200);
    });

    await page.goto("/patents");
    const listResponse = await listResponsePromise;
    const patents = (await listResponse.json()) as PatentListResponse;

    expect(
      patents.total,
      "publishable PostgreSQL patent count",
    ).toBeGreaterThan(0);
    expect(patents.items.length, "visible patent evidence records").toBe(
      patents.total,
    );
    expect(new Set(patents.items.map((patent) => patent.id)).size).toBe(
      patents.items.length,
    );

    for (const patent of patents.items) {
      expect(patent.id).toBe(patent.patent_number);
      expect(patent.analysis_id).toMatch(UUID_V4_PATTERN);
      expect(patent.title).toBeTruthy();

      const detailResponse = await page.request.get(
        `${LIVE_API_ORIGIN}/api/v1/patents/${encodeURIComponent(patent.id)}`,
        { headers: { Authorization: "Bearer dev-token" } },
      );
      expect(detailResponse.status()).toBe(200);
      const detail = (await detailResponse.json()) as PatentDetailResponse;
      expect(detail.analysis_id).toBe(patent.analysis_id);
      expect(detail.patent_analysis.patent_id).toBe(patent.id);
      expect(detail.patent_analysis.title).toBe(patent.title);
      expect(detail.patent_analysis.assignee).toBe(patent.assignee);

      await expect(
        page.getByText(patent.patent_number, { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText(patent.compound_name, { exact: true }).first(),
      ).toBeVisible();
      await expect(
        page.getByText(patent.title, { exact: true }).first(),
      ).toBeVisible();

      const reportLink = page.getByRole("link", {
        name: `Open patent evidence for ${patent.patent_number}`,
        exact: true,
      });
      const href = await reportLink.getAttribute("href");
      expect(href).toBeTruthy();
      const reportUrl = new URL(href ?? "", page.url());
      expect(reportUrl.pathname).toBe(`/analyses/${patent.analysis_id}/report`);
      expect(reportUrl.searchParams.get("tab")).toBe("patents");
      expect(reportUrl.searchParams.get("patent")).toBe(patent.patent_number);
    }
  });

  test("legal review queue renders live unassigned threads against authoritative analyses", async ({
    page,
  }) => {
    const queueResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(
        response,
        "GET",
        "/api/v1/comments/review-queue",
        200,
      );
    });

    await page.goto("/reviews?filter=unassigned");
    const queueResponse = await queueResponsePromise;
    const queue = (await queueResponse.json()) as ReviewQueueListResponse;

    expect(
      queue.counts.open_total,
      "seeded open review threads",
    ).toBeGreaterThan(0);
    expect(queue.counts.unassigned).toBe(queue.items.length);
    expect(
      queue.items.length,
      "visible unassigned review threads",
    ).toBeGreaterThan(0);

    const analysisResponse = await page.request.get(
      `${LIVE_API_ORIGIN}/api/v1/analyses`,
      { headers: { Authorization: "Bearer dev-token" } },
    );
    expect(analysisResponse.status()).toBe(200);
    const analyses = (await analysisResponse.json()) as AnalysisListResponse;
    const analysisById = new Map(
      analyses.items.map((analysis) => [analysis.id, analysis]),
    );

    for (const item of queue.items) {
      expect(item.id).toMatch(UUID_V4_PATTERN);
      expect(item.analysis_id).toMatch(UUID_V4_PATTERN);
      expect(item.assigned_to).toBeNull();
      const authoritativeAnalysis = analysisById.get(item.analysis_id);
      expect(
        authoritativeAnalysis,
        `${item.compound_name} queue thread resolves to a live analysis`,
      ).toBeDefined();
      expect(item.compound_name).toBe(authoritativeAnalysis?.compound_name);
      expect(item.analysis_status).toBe(authoritativeAnalysis?.status);

      const queueCard = page.getByRole("article").filter({
        has: page.getByText(item.body, { exact: true }),
      });
      await expect(queueCard).toHaveCount(1);
      await expect(
        queueCard.getByRole("heading", {
          name: item.compound_name,
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        queueCard.getByText("Unassigned", { exact: true }).first(),
      ).toBeVisible();

      const reportLink = queueCard.getByRole("link", {
        name: item.analysis_status === "completed" ? "Open report" : "View run",
        exact: true,
      });
      const href = await reportLink.getAttribute("href");
      expect(href).toBeTruthy();
      const destination = new URL(href ?? "", page.url());
      expect(destination.pathname).toBe(
        item.analysis_status === "completed"
          ? `/analyses/${item.analysis_id}/report`
          : `/analyses/${item.analysis_id}`,
      );
    }
  });

  test("API key creation and revocation persist through authoritative reloads", async ({
    page,
  }, testInfo) => {
    const keyName = `Live browser receipt ${testInfo.retry}-${Date.now()}`;
    const initialListPromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/api-keys", 200);
    });

    await page.goto("/settings");
    const initialListResponse = await initialListPromise;
    const initialList =
      (await initialListResponse.json()) as APIKeyListResponse;
    expect(initialList.total).toBeGreaterThanOrEqual(initialList.items.length);
    // A failed Playwright step must never preserve the one-time credential in
    // screenshots. The response contract is asserted without logging its value.
    await page.addStyleTag({
      content: "code { filter: blur(12px) !important; }",
    });

    await page.getByRole("button", { name: "New API Key" }).click();
    await page.getByLabel("Key Name").fill(keyName);

    const createResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "POST", "/api/v1/api-keys", 201);
    });
    await page.getByRole("button", { name: "Generate Key" }).click();
    const createResponse = await createResponsePromise;
    const created = (await createResponse.json()) as APIKeyCreatedResponse;

    expect(created.name).toBe(keyName);
    expect(created.id).toMatch(UUID_V4_PATTERN);
    expect(
      /^prv_live_[A-Za-z0-9_-]{43}$/u.test(created.secret_key),
      "one-time secret follows the namespaced credential contract",
    ).toBe(true);
    await expect(
      page.getByRole("heading", { name: "API key created" }),
    ).toBeVisible();
    await expect(page.getByText(keyName, { exact: true })).toBeVisible();

    const persistedListPromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/api-keys", 200);
    });
    await page.reload();
    const persistedListResponse = await persistedListPromise;
    const persistedList =
      (await persistedListResponse.json()) as APIKeyListResponse;
    expect(
      persistedList.items.some(
        (item) =>
          item.id === created.id && item.name === keyName && !item.revoked,
      ),
      "created API key survives a fresh browser navigation",
    ).toBe(true);
    await expect(page.getByText(keyName, { exact: true })).toBeVisible();

    await page
      .getByRole("button", { name: `Start revoke for ${keyName}` })
      .click();
    const revokeResponsePromise = page.waitForResponse((response) => {
      return isLiveApiResponse(
        response,
        "DELETE",
        `/api/v1/api-keys/${created.id}`,
        200,
      );
    });
    await page
      .getByRole("button", { name: `Confirm revoke for ${keyName}` })
      .click();
    const revokeResponse = await revokeResponsePromise;
    const revoked = (await revokeResponse.json()) as APIKeyRevokedResponse;
    expect(revoked.status).toBe("revoked");

    const revokedListPromise = page.waitForResponse((response) => {
      return isLiveApiResponse(response, "GET", "/api/v1/api-keys", 200);
    });
    await page.reload();
    const revokedListResponse = await revokedListPromise;
    const revokedList =
      (await revokedListResponse.json()) as APIKeyListResponse;
    expect(
      revokedList.items.some(
        (item) =>
          item.id === created.id && item.name === keyName && item.revoked,
      ),
      "revoked API key survives a fresh browser navigation",
    ).toBe(true);

    const keyRow = page.getByRole("row").filter({
      has: page.getByText(keyName, { exact: true }),
    });
    await expect(keyRow.getByText("Revoked", { exact: true })).toBeVisible();

    mkdirSync(dirname(LIVE_DATABASE_RECEIPT_PATH), { recursive: true });
    writeFileSync(
      LIVE_DATABASE_RECEIPT_PATH,
      `${JSON.stringify(
        {
          created_response_status: createResponse.status(),
          expected_revoked: true,
          key_id: created.id,
          key_name: keyName,
          revoked_response_status: revokeResponse.status(),
          schema_version: 1,
          verified_ui_at: new Date().toISOString(),
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  });
});
