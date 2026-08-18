import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import AxeBuilder from "@axe-core/playwright";
import { createServer, type Server } from "node:http";

const VIEWPORTS = [
  { name: "320px", width: 320, height: 812 },
  { name: "375px", width: 375, height: 812 },
  { name: "768px", width: 768, height: 1024 },
];
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const API_PORT = Number(process.env.PLAYWRIGHT_API_PORT ?? 18080);

const PUBLIC_ROUTES = [
  "/",
  "/trust",
  "/sample-reports",
  "/sample-reports/example-molecule-alpha",
  "/methodology",
  "/compare/adaptive-agentic",
  "/for-biotech-founders",
  "/privacy",
  "/terms",
];

const REPORT_SHARE_TOKEN = `report_${"r".repeat(36)}`;
const CLEAR_SHARE_TOKEN = `clear_${"c".repeat(37)}`;
const EXPIRED_SHARE_TOKEN = `expired_${"e".repeat(35)}`;
const MISSING_SHARE_TOKEN = `missing_${"m".repeat(35)}`;
const ERROR_SHARE_TOKEN = `error_${"x".repeat(37)}`;
const SHARED_REPORT_ROUTE = `/share/${REPORT_SHARE_TOKEN}`;
const SHARED_REPORT_STATE_ROUTES = [
  {
    route: SHARED_REPORT_ROUTE,
    heading: "Succinic acid",
    state: "ok",
  },
  {
    route: `/share/${CLEAR_SHARE_TOKEN}`,
    heading: "Caffeine",
    state: "clear",
  },
  {
    route: SHARED_REPORT_ROUTE,
    heading: "Verify intended recipient",
    state: "verification",
  },
  {
    route: `/share/${EXPIRED_SHARE_TOKEN}`,
    heading: "Share link expired",
    state: "expired",
  },
  {
    route: `/share/${MISSING_SHARE_TOKEN}`,
    heading: "Report not available",
    state: "not-found",
  },
  {
    route: `/share/${ERROR_SHARE_TOKEN}`,
    heading: "Shared report temporarily unavailable",
    state: "error",
  },
] as const;

const SHARE_PAYLOAD = {
  compound_name: "Succinic acid",
  report_id: "report-public-ui-qa",
  share_id: "grant-public-ui-qa",
  packet_version: "recipient-bound-share-v2",
  integrity_digest: "f".repeat(64),
  overall_risk: "high",
  blocking_patents_count: 3,
  total_patents_found: 2417,
  executive_summary:
    "Three material patent families need qualified counsel review before launch.",
  key_findings: [
    "US0000000001A1 overlaps the fermentation route.",
    "EP3456789B1 requires claim-chart review.",
  ],
  generated_at: "2026-04-09T11:24:00.000Z",
  key_patents: [
    {
      patent_number: "US0000000001A1",
      risk_level: "high",
      assignee: "Example Pharma",
      expiry: "2037-04-09",
    },
    {
      patent_number: "EP3456789B1",
      risk_level: "medium",
      assignee: "GenericCo",
      expiry: "2034-11-21",
    },
  ],
  source_coverage: ["pubchem_sdq", "patentsview"],
  jurisdiction_scope: ["US", "EP"],
  evidence_limitations: ["EP family context incomplete"],
  integrity_summary: {
    affected_patents_count: 2,
    recoverable_failures_count: 1,
    needs_review_count: 1,
    data_limitations_count: 1,
    source_caveats_count: 2,
    evidence_sufficient_for_clearance: false,
    metadata_inconsistent: false,
  },
  total_material_patents: 6,
  omitted_key_patents_count: 4,
  omitted_limitations_count: 1,
  standard_limitations: [
    "Markush and generic claim coverage may require manual claim construction.",
    "Prior-art exhaustiveness and validity opinions are outside this shared screening artifact.",
  ],
  intended_use:
    "Read-only external FTO screening packet for qualified patent counsel review.",
  ai_system_notice:
    "AI-assisted patent landscape analysis; outputs require human review before reliance.",
  reliance_boundary:
    "Not a legal clearance opinion or freedom-to-operate opinion.",
  review_status: "approved",
  share_expires_at: "2027-05-09T11:24:00.000Z",
  verified_recipient_email: "counsel@example.com",
  attributable_view_number: 1,
  verified_session_expires_at: "2027-01-13T12:30:00.000Z",
};

const CLEAR_SHARE_PAYLOAD = {
  compound_name: "Caffeine",
  report_id: "report-public-ui-qa-clear",
  share_id: "grant-public-ui-qa-clear",
  packet_version: "recipient-bound-share-v2",
  integrity_digest: "c".repeat(64),
  overall_risk: "clear",
  blocking_patents_count: 0,
  total_patents_found: 12,
  executive_summary:
    "No material blockers were identified in the current source set.",
  key_findings: ["Current source set did not surface blocking claims."],
  generated_at: "2026-04-10T09:15:00.000Z",
  key_patents: [],
  source_coverage: ["report evidence"],
  jurisdiction_scope: ["US"],
  evidence_limitations: ["Coverage remains preliminary until counsel review."],
  review_status: "approved",
  share_expires_at: "2027-05-10T09:15:00.000Z",
  verified_recipient_email: "counsel@example.com",
  attributable_view_number: 1,
  verified_session_expires_at: "2027-01-13T12:30:00.000Z",
};

async function reachSharedReportState(
  page: Page,
  state: (typeof SHARED_REPORT_STATE_ROUTES)[number]["state"],
) {
  if (state === "verification") return;
  await page.getByRole("button", { name: "Send verification code" }).click();
  if (state !== "ok" && state !== "clear") return;
  await page.getByLabel("8-digit verification code").fill("24681357");
  await page.getByRole("button", { name: "Verify and view report" }).click();
}

async function expectTargetSize(locator: Locator, label: string, minSize = 44) {
  await expect(locator, `${label} visible`).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} target box`).not.toBeNull();
  expect(box?.width ?? 0, `${label} target width`).toBeGreaterThanOrEqual(
    minSize,
  );
  expect(box?.height ?? 0, `${label} target height`).toBeGreaterThanOrEqual(
    minSize,
  );
}

let apiServer: Server | undefined;

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    const pathname = request.url
      ? new URL(request.url, "http://127.0.0.1").pathname
      : "/";

    if (pathname.startsWith("/share/")) {
      const [, shareSegment, token, action] = pathname.split("/");
      if (shareSegment !== "share" || !token) {
        response.writeHead(404, { "content-type": "application/json" });
        response.end(JSON.stringify({ detail: "Not found" }));
        return;
      }

      if (action === "challenge") {
        const challengeStatus =
          token === EXPIRED_SHARE_TOKEN
            ? 410
            : token === MISSING_SHARE_TOKEN
              ? 404
              : token === ERROR_SHARE_TOKEN
                ? 500
                : 200;
        response.writeHead(challengeStatus, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify({ status: "verification_sent" }));
        return;
      }

      if (action === "verify") {
        response.writeHead(200, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(
          JSON.stringify({
            access_secret: "A".repeat(43),
            access_expires_at: "2027-01-13T12:30:00.000Z",
          }),
        );
        return;
      }

      if (token === REPORT_SHARE_TOKEN) {
        response.writeHead(200, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify(SHARE_PAYLOAD));
        return;
      }

      if (token === CLEAR_SHARE_TOKEN) {
        response.writeHead(200, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify(CLEAR_SHARE_PAYLOAD));
        return;
      }

      if (token === EXPIRED_SHARE_TOKEN) {
        response.writeHead(410, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify({ detail: "Expired" }));
        return;
      }

      if (token === ERROR_SHARE_TOKEN) {
        response.writeHead(500, {
          "content-type": "application/json",
          "cache-control": "no-store",
        });
        response.end(JSON.stringify({ detail: "Temporary failure" }));
        return;
      }
    }

    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ detail: "Not found" }));
  });

  await new Promise<void>((resolve, reject) => {
    apiServer?.once("error", reject);
    apiServer?.listen(API_PORT, "127.0.0.1", () => resolve());
  });
});

test.afterAll(async () => {
  await new Promise<void>((resolve, reject) => {
    if (!apiServer?.listening) {
      resolve();
      return;
    }
    apiServer.close((error) => (error ? reject(error) : resolve()));
  });
});

test.describe("Public UI QA", () => {
  test.describe.configure({ mode: "serial" });

  test("public legal and share routes avoid duplicate Praviar title branding", async ({
    page,
  }) => {
    for (const route of ["/privacy", "/terms", SHARED_REPORT_ROUTE]) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");

      const title = await page.title();
      const brandMentions = title.match(/\bPraviar\b/gu)?.length ?? 0;

      expect(title, `${route} rendered title`).not.toMatch(
        /Praviar\s*(?:\||—|-)\s*Praviar/u,
      );
      expect(
        brandMentions,
        `${route} Praviar title mentions`,
      ).toBeLessThanOrEqual(1);
    }
  });

  for (const viewport of VIEWPORTS) {
    test(`public routes have no horizontal overflow at ${viewport.name}`, async ({
      page,
      request,
    }) => {
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") {
          consoleErrors.push(message.text());
        }
      });

      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });

      // Compile every App Router entry before the browser joins the dev HMR
      // session. This keeps the strict fixture focused on application failures
      // instead of route-compilation hot-update replacements.
      for (const route of PUBLIC_ROUTES) {
        const response = await request.get(route);
        expect(response.ok(), `${route} warm-up response`).toBe(true);
      }

      for (const route of PUBLIC_ROUTES) {
        await page.goto(route);
        await page.waitForLoadState("networkidle");

        const overflow = await page.evaluate(
          () =>
            Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
            ) - window.innerWidth,
        );

        expect(
          overflow,
          `${route} overflow at ${viewport.name}`,
        ).toBeLessThanOrEqual(1);
      }

      expect(consoleErrors).toEqual([]);
    });
  }

  test("fictional sample pages disclose their status without live-proof copy", async ({
    page,
  }) => {
    await page.goto("/sample-reports/example-molecule-alpha");

    await expect(
      page
        .getByText("Fictional product sample")
        .filter({ visible: true })
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/live proof/i)).toHaveCount(0);
    await expect(page.getByText(/live report surface/i)).toHaveCount(0);

    // Let the self-hosted molecule renderer finish before replacing the
    // document. This keeps the strict browser gate focused on real resource
    // failures instead of an intentional navigation cancelling an in-flight
    // dynamic import/WASM response.
    await expect(
      page.getByRole("img", {
        name: /Molecular structure of Example Molecule Alpha/i,
      }),
    ).toBeVisible({ timeout: 15_000 });

    await page.goto("/");
    await expect(
      page.getByRole("heading", {
        name: "See which patent families may change your next move.",
      }),
    ).toBeVisible();
    await expect(page.getByText(/live proof/i)).toHaveCount(0);
    await expect(page.getByText(/profile=adaptive/i)).toHaveCount(0);
  });

  test("trust page uses a lightweight governed visual without mobile overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/trust");
    await page.waitForLoadState("networkidle");

    const visual = page.getByTestId("trust-control-visual");
    await expect(
      page.getByRole("heading", {
        name: "Know what Praviar can protect and prove before you use it.",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /see how praviar works/i }),
    ).toBeVisible();
    await expect(visual).toBeVisible();
    await expect(visual).toContainText("The work stays visible");
    await expect(visual).toContainText("Claims, citations, source health");
    await expect(page.getByTestId("trust-boundary-artifact")).toContainText(
      "Qualified counsel review",
    );

    const metrics = await page.evaluate(() => {
      const image = document.querySelector(
        '[data-testid="trust-control-visual"] img',
      ) as HTMLImageElement | null;
      const resources = performance
        .getEntriesByType("resource")
        .filter((entry) =>
          entry.name.includes("controlled-review-workspace-v1.webp"),
        ) as PerformanceResourceTiming[];

      return {
        overflow:
          Math.max(
            document.body.scrollWidth,
            document.documentElement.scrollWidth,
          ) - window.innerWidth,
        imageSource: image?.currentSrc ?? image?.src ?? "",
        imageWidth: image?.naturalWidth ?? 0,
        bytes: resources.reduce(
          (total, entry) =>
            total + (entry.transferSize || entry.encodedBodySize || 0),
          0,
        ),
        resourceCount: resources.length,
      };
    });

    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.imageSource).toContain(
      "controlled-review-workspace-v1.webp",
    );
    expect(metrics.imageWidth).toBeGreaterThan(0);
    expect(metrics.resourceCount).toBeGreaterThan(0);
    expect(metrics.bytes).toBeLessThanOrEqual(200_000);
  });

  test("legal pages keep one main landmark and mobile-readable document structure", async ({
    page,
  }) => {
    for (const route of ["/privacy", "/terms"]) {
      await page.setViewportSize({ width: 320, height: 812 });
      await page.goto(route);
      await page.waitForLoadState("networkidle");

      await expect(page.locator("main")).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(
        page.getByText("Last updated: August 13, 2026"),
      ).toBeVisible();
      const mobileDocument = page.getByTestId("mobile-legal-document");
      const sectionDisclosure = page.getByRole("button", {
        name: "Jump to a section",
      });
      await expect(sectionDisclosure).toBeVisible();
      await expect(mobileDocument).toBeVisible();

      const metrics = await page.evaluate(() => {
        const article = document.querySelector(
          "[data-testid='mobile-legal-document']",
        );
        const articleRect = article?.getBoundingClientRect();

        return {
          overflow:
            Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
            ) - window.innerWidth,
          articleWidth: articleRect?.width ?? 0,
          h1Count: document.querySelectorAll("h1").length,
        };
      });

      expect(metrics.overflow, `${route} overflow`).toBeLessThanOrEqual(1);
      expect(metrics.articleWidth, `${route} article width`).toBeGreaterThan(
        260,
      );
      expect(metrics.h1Count, `${route} h1 count`).toBe(1);

      await sectionDisclosure.click();
      const mobileSectionNav = page.getByRole("navigation", {
        name: "Mobile legal document sections",
      });
      await expect(mobileSectionNav).toBeVisible();
      await expectTargetSize(
        mobileSectionNav.getByRole("link").first(),
        `${route} section nav link`,
      );

      if (route === "/privacy") {
        await mobileSectionNav
          .getByRole("link", {
            name: "6. Security and confidentiality boundary",
          })
          .click();
        await expectTargetSize(
          page.getByRole("link", { name: "Review evidence boundaries" }),
          `${route} contact link`,
        );
        await expect(
          page.getByText("Not represented by this page"),
        ).toBeVisible();
        await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
      } else {
        await mobileSectionNav
          .getByRole("link", { name: "3. No legal advice or reliance" })
          .click();
        await expectTargetSize(
          page.getByRole("link", { name: "Review the methodology" }),
          `${route} contact link`,
        );
        await expect(
          mobileDocument.getByText("No service. No contract. No legal advice."),
        ).toBeVisible();
        await expect(
          mobileDocument.getByText(/not a law firm/i).first(),
        ).toBeVisible();
        await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
      }
    }
  });

  test("legal section navigation remains sticky without clipping ancestors on desktop", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });

    for (const route of ["/privacy", "/terms"]) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");

      const sectionNav = page.getByRole("navigation", {
        name: "Legal document sections",
      });
      const sectionNavShell = page.getByTestId(
        "legal-document-section-nav-shell",
      );
      await expect(sectionNav).toBeVisible();
      await expect(sectionNavShell).toBeVisible();

      await page.evaluate(() => {
        const maxScroll = Math.max(
          0,
          document.documentElement.scrollHeight - window.innerHeight,
        );
        window.scrollTo(0, Math.min(760, maxScroll));
      });

      const stickyMetrics = await sectionNavShell.evaluate((element) => {
        const verticalClippingAncestors: string[] = [];
        let parent = element.parentElement;

        while (
          parent &&
          parent !== document.body &&
          parent !== document.documentElement
        ) {
          const style = window.getComputedStyle(parent);
          const clipsSticky = /(?:hidden|auto|scroll|clip)/u.test(
            style.overflowY,
          );

          if (clipsSticky) {
            verticalClippingAncestors.push(
              parent.id
                ? `${parent.tagName.toLowerCase()}#${parent.id}`
                : parent.tagName.toLowerCase(),
            );
          }

          parent = parent.parentElement;
        }

        const rect = element.getBoundingClientRect();
        const navRect = element.querySelector("nav")?.getBoundingClientRect();
        const articleRect = document
          .querySelector("[data-testid='legal-document']")
          ?.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return {
          position: style.position,
          computedTop: Number.parseFloat(style.top) || 0,
          scrollY: window.scrollY,
          rectTop: rect.top,
          navRight: navRect?.right ?? 0,
          articleLeft: articleRect?.left ?? Number.POSITIVE_INFINITY,
          verticalClippingAncestors,
        };
      });

      expect(stickyMetrics.position, `${route} nav container position`).toBe(
        "sticky",
      );
      expect(
        stickyMetrics.verticalClippingAncestors,
        `${route} sticky vertical clipping ancestors`,
      ).toEqual([]);
      expect(
        stickyMetrics.navRight,
        `${route} nav right edge`,
      ).toBeLessThanOrEqual(stickyMetrics.articleLeft);
      if (stickyMetrics.scrollY > 32) {
        expect(
          Math.abs(stickyMetrics.rectTop - stickyMetrics.computedTop),
          `${route} sticky top offset`,
        ).toBeLessThanOrEqual(2);
      }
    }
  });

  test("open-source project section stays truthful and action-oriented", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const project = page.locator("#project");
    await project.scrollIntoViewIfNeeded();
    const surfaces = page.getByTestId("project-surface-grid");

    await expect(project).toBeVisible();
    await expect(surfaces).toContainText("Next.js workbench");
    await expect(surfaces).toContainText("FastAPI service");
    await expect(surfaces).toContainText("Research pipeline");
    await expect(surfaces).toContainText("Evaluation system");
    await expect(
      project.getByRole("link", { name: "View source on GitHub" }),
    ).toHaveAttribute(
      "href",
      "https://github.com/Peter-McCann-Strain/chemical-patent-analysis",
    );
    await expect(project).toContainText("working open-source research system");
  });

  for (const viewport of [
    { name: "320px", width: 320, height: 812 },
    { name: "768px", width: 768, height: 1024 },
  ]) {
    test(`open-source project section has no horizontal overflow at ${viewport.name}`, async ({
      page,
    }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.goto("/#project");
      await page.waitForLoadState("networkidle");
      await page.locator("#project").scrollIntoViewIfNeeded();
      const surfaces = page.getByTestId("project-surface-grid");
      await expect(surfaces).toBeVisible();
      await expect(
        page.getByRole("link", { name: "View source on GitHub" }).last(),
      ).toBeVisible();

      const metrics = await page.evaluate(() => {
        const project = document.querySelector("#project");
        const grid = document.querySelector(
          "[data-testid='project-surface-grid']",
        );
        return {
          bodyOverflow:
            Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
            ) - window.innerWidth,
          projectOverflow: project && project.scrollWidth - project.clientWidth,
          gridOverflow: grid && grid.scrollWidth - grid.clientWidth,
        };
      });

      expect(metrics.bodyOverflow).toBeLessThanOrEqual(1);
      expect(metrics.projectOverflow ?? 0).toBeLessThanOrEqual(1);
      expect(metrics.gridOverflow ?? 0).toBeLessThanOrEqual(1);
    });
  }

  test("sample report mobile preview leads with patent evidence before molecule art", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/sample-reports/example-molecule-alpha");
    await page.waitForLoadState("networkidle");

    const disclosureTrigger = page.getByRole("button", {
      name: /inspect synthetic dossier evidence/i,
    });
    const dossier = page
      .getByTestId("fto-dossier-preview")
      .filter({ visible: true })
      .first();
    const leadEvidence = page
      .getByTestId("fto-dossier-lead-evidence")
      .filter({ visible: true })
      .first();
    const visual = page
      .getByTestId("fto-dossier-visual")
      .filter({ visible: true })
      .first();
    await expect(
      page.getByTestId("sample-report-detail-brand-lockup"),
    ).toHaveCount(0);
    await expect(disclosureTrigger).toBeVisible();
    await expect(disclosureTrigger).toHaveAttribute("aria-expanded", "false");
    await disclosureTrigger.click();
    await expect(disclosureTrigger).toHaveAttribute("aria-expanded", "true");
    await expect(dossier).toBeVisible();
    await expect(leadEvidence).toBeVisible();
    await expect(leadEvidence).toContainText("Lead evidence");
    await expect(leadEvidence).toContainText(/Claim \d+/);
    await expect(visual).toBeVisible();

    const [leadBox, visualBox, layout] = await Promise.all([
      leadEvidence.boundingBox(),
      visual.boundingBox(),
      page.evaluate(() => {
        const hero = document.querySelector(".praviar-report-hero-field");
        const heroBackground = hero
          ? window.getComputedStyle(hero).backgroundImage
          : "";

        return {
          heroBackground,
          overflow:
            Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
            ) - window.innerWidth,
        };
      }),
    ]);

    expect(leadBox).not.toBeNull();
    expect(visualBox).not.toBeNull();
    expect(leadBox!.y).toBeLessThan(visualBox!.y);
    expect(layout.heroBackground).toContain("praviar-evidence-desk-field-v2");
    expect(layout.overflow).toBeLessThanOrEqual(1);
  });

  for (const viewport of [
    { name: "320px", width: 320, height: 812 },
    { name: "375px", width: 375, height: 812 },
    { name: "390px", width: 390, height: 844 },
  ]) {
    test(`homepage mobile hero leads with proof, input, and actions at ${viewport.name}`, async ({
      page,
    }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.goto("/");
      await page.waitForLoadState("networkidle");

      const heroProof = page.getByTestId("homepage-hero-proof");
      const brandLockup = page.getByTestId("homepage-hero-brand-lockup");
      const caveat = page.getByTestId("homepage-hero-caveat");
      const evidenceTrace = page.getByTestId("homepage-hero-evidence-trace");
      const compoundInput = page.locator("#hero-compound");
      const cta = page
        .getByTestId("homepage-mobile-compound-entry")
        .getByRole("link", { name: "Run a known compound" });
      const sampleLink = page.getByRole("link", {
        name: "See the sample dossier",
      });
      const creditPackLink = page.getByRole("link", {
        name: "See pricing",
      });

      await expect(
        page.getByRole("heading", {
          level: 1,
          name: "See which patent families may change your next move.",
        }),
      ).toBeVisible();
      await expect(heroProof).toBeVisible();
      await expect(brandLockup).not.toBeVisible();
      await expect(
        page.getByRole("link", { name: "Praviar home" }),
      ).toBeVisible();
      await expect(heroProof).toContainText("Sample dossier output");
      await expect(heroProof).toContainText("3");
      await expect(heroProof).toContainText("2,417");
      await expect(heroProof).toContainText("47");
      await expect(caveat).toBeVisible();
      await expect(caveat).toContainText("Fictional product sample");
      await expect(caveat).toContainText("Not a legal opinion");
      await expect(evidenceTrace).not.toBeVisible();
      await expect(compoundInput).toBeVisible();
      await expect(compoundInput).toHaveAttribute(
        "placeholder",
        /Paste compound/,
      );
      await compoundInput.fill("remdesivir");
      const ctaHref = await cta.getAttribute("href");
      expect(ctaHref).not.toBeNull();
      const ctaUrl = new URL(ctaHref!, page.url());
      expect(ctaUrl.pathname).toBe("/sign-up");
      const returnTo = ctaUrl.searchParams.get("return_to");
      expect(returnTo).not.toBeNull();
      expect(
        new URL(returnTo!, "http://praviar.local").searchParams.get("compound"),
      ).toBeNull();
      expect(ctaHref).not.toContain("remdesivir");
      await expect(cta).toBeVisible();
      await expect(sampleLink).toBeVisible();
      await expect(creditPackLink).toHaveAttribute("href", "#pricing");
      await expect(creditPackLink).toBeVisible();
      await expectTargetSize(cta, `${viewport.name} primary hero action`);
      await expectTargetSize(
        sampleLink,
        `${viewport.name} sample dossier action`,
      );
      await expectTargetSize(
        creditPackLink,
        `${viewport.name} credit pack action`,
      );

      const layout = await page.evaluate(() => {
        const cta = Array.from(document.querySelectorAll("a")).find((link) =>
          link.textContent?.includes("Run a known compound"),
        );
        const input =
          document.querySelector<HTMLInputElement>("#hero-compound");
        const hero = document.querySelector(".praviar-hero-field");
        const mark = document.querySelector(
          "[data-testid='homepage-hero-brand-lockup'] svg",
        );
        const ctaBox = cta?.getBoundingClientRect();
        const inputBox = input?.getBoundingClientRect();
        const heroBox = hero?.getBoundingClientRect();
        const markBox = mark?.getBoundingClientRect();
        const heroBackground = hero
          ? window.getComputedStyle(hero).backgroundImage
          : "";
        const inputVisible =
          !!input &&
          !!inputBox &&
          inputBox.width > 0 &&
          inputBox.height > 0 &&
          window.getComputedStyle(input).visibility !== "hidden";

        return {
          overflow:
            Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
            ) - window.innerWidth,
          ctaBottom: ctaBox?.bottom ?? 0,
          inputHeight: inputVisible ? (inputBox?.height ?? 0) : 0,
          inputVisible,
          markHeight: markBox?.height ?? 0,
          heroBackground,
          heroHeight: heroBox?.height ?? 0,
          viewportHeight: window.innerHeight,
        };
      });

      expect(layout.overflow).toBeLessThanOrEqual(1);
      expect(layout.ctaBottom).toBeLessThanOrEqual(layout.viewportHeight);
      expect(layout.inputVisible).toBe(true);
      expect(layout.inputHeight).toBeGreaterThanOrEqual(44);
      expect(layout.markHeight).toBe(0);
      expect(layout.heroBackground).toContain("praviar-hero-evidence.svg");
      expect(layout.heroHeight).toBeLessThanOrEqual(1650);
    });
  }

  test.describe("shared report state contracts", () => {
    test.use({
      // This suite deliberately renders the API 500 state. Keep the exception
      // exact and local; every other console error remains fatal.
      allowedConsoleErrorPrefixes: ["%c%s%c [SharedReport] API returned"],
    });

    test("public shared report states keep external handoff caveats visible", async ({
      page,
    }) => {
      for (const viewport of VIEWPORTS) {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });

        for (const shareState of SHARED_REPORT_STATE_ROUTES) {
          await page.goto(shareState.route);
          await page.waitForLoadState("networkidle");
          await reachSharedReportState(page, shareState.state);

          await expect(
            page.getByRole("heading", { level: 1, name: shareState.heading }),
          ).toBeVisible();
          await expect(
            page.getByText("External shared FTO packet"),
          ).toBeVisible();
          await expect(page.getByText("Read-only external view")).toBeVisible();
          await expect(page.getByText("No workspace edits")).toBeVisible();
          await expect(
            page.getByText("No legal clearance opinion").first(),
          ).toBeVisible();

          const metrics = await page.evaluate(() => {
            const ids = Array.from(document.querySelectorAll("[id]"))
              .map((element) => element.id)
              .filter(Boolean);
            const duplicateIds = ids.filter(
              (id, index) => ids.indexOf(id) !== index,
            );

            return {
              overflow:
                Math.max(
                  document.body.scrollWidth,
                  document.documentElement.scrollWidth,
                ) - window.innerWidth,
              mainCount: document.querySelectorAll("main").length,
              h1Count: document.querySelectorAll("h1").length,
              duplicateIds,
              readableHeadingWidth:
                (
                  document.querySelector("[data-praviar-share-access] h1") ??
                  document.querySelector(
                    "main > div > header h1, main > div > header p.type-heading-xl",
                  )
                )?.getBoundingClientRect().width ?? 0,
              shellWordmark: (() => {
                const wordmark = Array.from(
                  document.querySelectorAll("[data-praviar-wordmark]"),
                ).find((element) => element.textContent?.trim() === "Praviar");
                const box = wordmark?.getBoundingClientRect();
                const lineHeight = wordmark
                  ? Number.parseFloat(
                      window.getComputedStyle(wordmark).lineHeight,
                    )
                  : 0;

                return {
                  height: box?.height ?? 0,
                  lineHeight,
                  width: box?.width ?? 0,
                };
              })(),
              nestedInteractiveCount: document.querySelectorAll(
                "a[href] button, button a[href], a[href] [role='button'], [role='button'] a[href], button button",
              ).length,
            };
          });

          expect(
            metrics.overflow,
            `${shareState.route} overflow at ${viewport.name}`,
          ).toBeLessThanOrEqual(1);
          expect(metrics.mainCount, `${shareState.route} main count`).toBe(1);
          expect(metrics.h1Count, `${shareState.route} h1 count`).toBe(1);
          expect(
            metrics.readableHeadingWidth,
            `${shareState.route} readable heading width at ${viewport.name}`,
          ).toBeGreaterThan(Math.min(200, viewport.width - 120));
          expect(
            metrics.shellWordmark.width,
            `${shareState.route} Praviar wordmark width at ${viewport.name}`,
          ).toBeGreaterThan(60);
          expect(
            metrics.shellWordmark.height,
            `${shareState.route} Praviar wordmark should not wrap at ${viewport.name}`,
          ).toBeLessThanOrEqual(metrics.shellWordmark.lineHeight * 1.35);
          expect(
            metrics.duplicateIds,
            `${shareState.route} duplicate IDs`,
          ).toEqual([]);
          expect(
            metrics.nestedInteractiveCount,
            `${shareState.route} nested controls`,
          ).toBe(0);

          if (shareState.state === "ok" || shareState.state === "clear") {
            await expect(
              page.getByText("Shared preliminary report"),
            ).toBeVisible();
            await expect(
              page.getByText(/does not provide a legal clearance opinion/i),
            ).toBeVisible();
            const reportControls = await page
              .locator(
                "[data-praviar-share-report] button, [data-praviar-share-report] a[href], [data-praviar-share-report] [role='button']",
              )
              .count();
            expect(reportControls, "shared report controls").toBe(0);

            await page.evaluate(() => {
              const trustBar = document.querySelector(
                "[data-praviar-share-trust-bar]",
              );
              const maxScroll = Math.max(
                0,
                document.documentElement.scrollHeight - window.innerHeight,
              );
              const trustBarTop = trustBar
                ? window.scrollY + trustBar.getBoundingClientRect().top
                : 0;
              window.scrollTo(0, Math.min(trustBarTop + 96, maxScroll));
            });

            const trustMetrics = await page
              .locator("[data-praviar-share-trust-bar]")
              .evaluate((element) => {
                const verticalClippingAncestors: string[] = [];
                let parent = element.parentElement;

                while (
                  parent &&
                  parent !== document.body &&
                  parent !== document.documentElement
                ) {
                  const style = window.getComputedStyle(parent);
                  const clipsSticky = /(?:hidden|auto|scroll|clip)/u.test(
                    style.overflowY,
                  );

                  if (clipsSticky) {
                    verticalClippingAncestors.push(
                      parent.id
                        ? `${parent.tagName.toLowerCase()}#${parent.id}`
                        : parent.tagName.toLowerCase(),
                    );
                  }

                  parent = parent.parentElement;
                }

                const rect = element.getBoundingClientRect();
                return {
                  position: window.getComputedStyle(element).position,
                  scrollY: window.scrollY,
                  top: rect.top,
                  height: rect.height,
                  viewportHeight: window.innerHeight,
                  verticalClippingAncestors,
                };
              });

            if (viewport.width >= 768) {
              expect(
                trustMetrics.position,
                `${shareState.route} trust position`,
              ).toBe("sticky");
              expect(
                trustMetrics.verticalClippingAncestors,
                `${shareState.route} sticky clipping ancestors`,
              ).toEqual([]);
            } else {
              expect(
                trustMetrics.position,
                `${shareState.route} mobile trust position`,
              ).toBe("static");
              expect(
                trustMetrics.height,
                `${shareState.route} mobile trust height`,
              ).toBeLessThanOrEqual(trustMetrics.viewportHeight * 0.34);
            }

            if (
              trustMetrics.position === "sticky" &&
              trustMetrics.scrollY > 32
            ) {
              expect(
                trustMetrics.top,
                `${shareState.route} sticky top`,
              ).toBeGreaterThanOrEqual(0);
              expect(
                trustMetrics.top,
                `${shareState.route} sticky top`,
              ).toBeLessThanOrEqual(16);
            }
          }

          if (shareState.state === "ok") {
            await expect(
              page
                .getByText("Partial evidence: counsel verification required")
                .first(),
            ).toBeVisible();
            await expect(page.getByText("2 affected")).toBeVisible();
            await expect(
              page.getByText("2 of 6 reviewed patents shown").first(),
            ).toBeVisible();
            await expect(
              page.getByText(
                "1 additional caveat omitted from this compact public view.",
              ),
            ).toBeVisible();
            await expect(
              page.locator("p", { hasText: /^US, EP$/ }),
            ).toBeVisible();
            await expect(
              page.locator("p", { hasText: /^PubChem SDQ, PatentsView$/ }),
            ).toBeVisible();
          }

          if (shareState.state === "clear") {
            await expect(
              page.getByText("NO BLOCKERS SURFACED").first(),
            ).toBeVisible();
            await expect(page.getByText(/^CLEAR$/)).toHaveCount(0);
            await expect(page.locator("p", { hasText: /^US$/ })).toBeVisible();
            await expect(
              page.locator("p", { hasText: /^report evidence$/ }),
            ).toBeVisible();
          }

          if (shareState.state === "verification") {
            await expectTargetSize(
              page.getByRole("button", { name: "Send verification code" }),
              `${shareState.route} verification request`,
            );
          }
        }
      }
    });

    test("public shared report states pass an axe smoke check", async ({
      page,
    }) => {
      await page.setViewportSize({ width: 390, height: 844 });

      for (const shareState of SHARED_REPORT_STATE_ROUTES) {
        await page.goto(shareState.route);
        await page.waitForLoadState("networkidle");
        await reachSharedReportState(page, shareState.state);

        const results = await new AxeBuilder({ page })
          .withTags(WCAG_TAGS)
          .analyze();

        expect(
          results.violations,
          `${shareState.route} axe violations`,
        ).toEqual([]);
      }
    });
  });
});
