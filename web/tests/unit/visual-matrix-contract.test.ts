import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DEMO_SHARE_TOKEN } from "../../src/lib/demo-data";
import {
  DEMO_ONBOARDING_IDENTITY,
  DEV_ONBOARDING_IDENTITY,
  onboardingStorageKeys,
} from "../../src/lib/onboarding-storage";
import { visualMatrixOnboardingIdentityForProfile } from "../e2e/fixtures/visual-matrix-browser-isolation";
import {
  VISUAL_MATRIX_API_KEY_ID,
  VISUAL_MATRIX_API_REPORT_ID,
  VISUAL_MATRIX_CAPTURE_ROUTES,
  VISUAL_MATRIX_CAPTURE_SURFACES,
  VISUAL_MATRIX_COMMENT_ID,
  VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID,
  VISUAL_MATRIX_MONITOR_ALERT_ID,
  VISUAL_MATRIX_MONITOR_ID,
  VISUAL_MATRIX_REDIRECT_ROUTES,
  VISUAL_MATRIX_ROUTES,
  visualMatrixSurfacesForProfile,
} from "../e2e/fixtures/visual-matrix-routes";

function collectPageSources(directory: string, prefix = "src/app"): string[] {
  const sources: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const entryPath = resolve(directory, entry.name);
    const sourcePath = `${prefix}/${entry.name}`;
    if (entry.isDirectory()) {
      sources.push(...collectPageSources(entryPath, sourcePath));
    } else if (entry.name === "page.tsx") {
      sources.push(sourcePath);
    }
  }
  return sources.sort();
}

describe("visual matrix route contract", () => {
  it("uses the runtime profile's scoped onboarding identity", () => {
    expect(visualMatrixOnboardingIdentityForProfile("demo")).toBe(
      DEMO_ONBOARDING_IDENTITY,
    );
    expect(visualMatrixOnboardingIdentityForProfile("api")).toBe(
      DEV_ONBOARDING_IDENTITY,
    );
    expect(
      onboardingStorageKeys(visualMatrixOnboardingIdentityForProfile("demo")),
    ).not.toEqual(
      onboardingStorageKeys(visualMatrixOnboardingIdentityForProfile("api")),
    );
  });

  it("maps every app-router page exactly once", () => {
    const routeSources = VISUAL_MATRIX_ROUTES.map(
      (route) => route.sourcePage,
    ).sort();
    expect(VISUAL_MATRIX_ROUTES).toHaveLength(38);
    expect(new Set(routeSources).size).toBe(routeSources.length);
    expect(routeSources).toEqual(
      collectPageSources(resolve(process.cwd(), "src/app")),
    );
  });

  it("requires unique capture names, requested routes, and rendered sentinels", () => {
    expect(new Set(VISUAL_MATRIX_ROUTES.map((route) => route.name)).size).toBe(
      38,
    );
    expect(new Set(VISUAL_MATRIX_ROUTES.map((route) => route.path)).size).toBe(
      38,
    );
    for (const route of VISUAL_MATRIX_ROUTES) {
      expect(route.expectedPath).toMatch(/^\//u);
      expect(route.sentinels.length, route.name).toBeGreaterThan(0);
      for (const sentinel of route.sentinels) {
        expect(
          "name" in sentinel ? sentinel.name : sentinel.value,
          route.name,
        ).not.toBe("");
      }
    }
  });

  it("binds every post-action buyer surface as a distinct capture state", () => {
    expect(VISUAL_MATRIX_CAPTURE_ROUTES).toHaveLength(34);
    expect(VISUAL_MATRIX_CAPTURE_SURFACES).toHaveLength(130);
    expect(
      new Set(VISUAL_MATRIX_CAPTURE_SURFACES.map((surface) => surface.name))
        .size,
    ).toBe(130);

    const gate = VISUAL_MATRIX_ROUTES.find((route) => route.name === "share");
    const verified = VISUAL_MATRIX_CAPTURE_SURFACES.find(
      (surface) => surface.name === "share-verified",
    );
    expect(gate?.path).toBe(`/share/${DEMO_SHARE_TOKEN}`);
    expect(verified).toMatchObject({
      path: gate?.path,
      expectedPath: gate?.expectedPath,
      sourcePage: gate?.sourcePage,
    });
    expect(verified?.sentinels).toContainEqual({
      kind: "text",
      value: "Attributable verified view",
    });

    expect(
      VISUAL_MATRIX_CAPTURE_SURFACES.slice(
        VISUAL_MATRIX_CAPTURE_ROUTES.length,
      ).map((surface) => surface.name),
    ).toEqual([
      "report-tab-patents",
      "report-tab-claims",
      "report-tab-evidence",
      "report-tab-invalidity",
      "report-tab-comments",
      "report-tab-drawings",
      "report-tab-regulatory",
      "report-tab-audit",
      "report-tab-meta",
      "report-tab-reasoning",
      "share-verified",
      "sender-share-success",
      "share-activity-expanded",
      "share-revoke-confirm",
      "approved-domains-policy",
      "analysis-launch-review",
      "analysis-identity-unconfirmed",
      "analysis-identity-confirmed",
      "analysis-launch-submitted",
      "first-run-welcome",
      "billing-credit-intent",
      "billing-purchase-terms-expanded",
      "command-palette",
      "dashboard-ai-actions-expanded",
      "monitor-create",
      "batch-create",
      "blocked-export-recovery",
      "report-export-ready",
      "batch-cancel-confirm",
      "review-bulk-confirm",
      "admin-clerk-operation-unconfirmed",
      "admin-clerk-operation-reconciled",
      "admin-clerk-operation-rejected",
      "admin-clerk-authority-unsynchronized",
      "share-delivery-outcome-unknown",
      "share-delivery-outcome-cancel-confirm",
      "share-delivery-refresh-resolved",
      "share-delivery-reconciliation-alert",
      "share-delivery-cancelled-retention",
      "external-share-link-unavailable",
      "external-share-verification-error",
      "billing-credit-checkout-return-reconciling",
      "billing-credit-ledger-reconciled",
      "billing-credit-checkout-cancelled",
      "billing-credit-checkout-failure",
      "auth-checkout-intent-signed-out",
      "admin-users-invite",
      "admin-organizations",
      "admin-ops-snapshot",
      "admin-audit-logs",
      "admin-tasks",
      "admin-users-role-review",
      "admin-users-restricted",
      "billing-actions-restricted",
      "billing-stale-data",
      "billing-invoice-unavailable",
      "analysis-capacity-blocked",
      "analysis-running",
      "analysis-failed",
      "analyses-empty",
      "report-patent-detail-open",
      "report-citation-source-open",
      "report-claim-decision-source-review",
      "review-decision-save-failure",
      "report-review-decision-saved",
      "report-review-lifecycle-transition",
      "report-coverage-recovery",
      "settings-api-key-reveal",
      "settings-api-key-revoke-confirm",
      "settings-sso-config-failure",
      "analyses-load-failure",
      "patents-load-failure",
      "compounds-load-failure",
      "reviews-load-failure",
      "monitors-load-failure",
      "batch-load-failure",
      "monitor-alert-history",
      "monitor-delete-confirm",
      "batch-detail-partial",
      "settings-sso-active",
      "report-chat-success",
      "report-chat-failure",
      "report-comments-load-failure",
      "report-watch-active",
      "billing-plan-checkout-failure",
      "billing-portal-failure",
      "session-expired",
      "report-comment-post-outcome-unknown",
      "report-resolution-outcome-unknown",
      "report-watch-start-outcome-unknown",
      "monitor-pause-outcome-unknown",
      "monitor-delete-outcome-unknown",
      "monitor-alert-dismiss-outcome-unknown",
      "settings-api-key-create-outcome-unknown",
      "settings-api-key-revoke-outcome-unknown",
      "settings-notification-save-outcome-unknown",
    ]);
  });

  it("partitions the 520-capture inventory into deterministic runtime profiles", () => {
    expect(visualMatrixSurfacesForProfile("demo")).toHaveLength(90);
    expect(visualMatrixSurfacesForProfile("api")).toHaveLength(40);
    expect(
      (visualMatrixSurfacesForProfile("demo").length +
        visualMatrixSurfacesForProfile("api").length) *
        4,
    ).toBe(520);
  });

  it("binds the new disclosure and source-review interactions to exact sentinels", () => {
    const dashboardDisclosure = VISUAL_MATRIX_CAPTURE_SURFACES.find(
      (surface) => surface.name === "dashboard-ai-actions-expanded",
    );
    expect(dashboardDisclosure).toMatchObject({
      expectedPath: "/dashboard",
      path: "/dashboard",
      sourcePage: "src/app/(dashboard)/dashboard/page.tsx",
    });
    expect(dashboardDisclosure?.profile ?? "demo").toBe("demo");
    expect(dashboardDisclosure?.sentinels).toEqual(
      expect.arrayContaining([
        { kind: "testId", value: "dashboard-ai-command-disclosure" },
        { kind: "testId", value: "dashboard-ai-command-panel" },
        { kind: "text", value: "Claim-cited output" },
        { kind: "text", value: "Human review gate" },
        { kind: "text", value: "Tenant-scoped context" },
      ]),
    );

    const claimSourceReview = VISUAL_MATRIX_CAPTURE_SURFACES.find(
      (surface) => surface.name === "report-claim-decision-source-review",
    );
    expect(claimSourceReview).toMatchObject({
      expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
      path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
      profile: "api",
      sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    });
    expect(claimSourceReview?.sentinels).toEqual(
      expect.arrayContaining([
        { kind: "testId", value: "claim-decision-matrix" },
        { kind: "text", value: "Inspect provenance receipt" },
        { kind: "text", value: "2 · AI-assisted inference" },
        { kind: "text", value: "3 · Human decision" },
        { kind: "text", value: "Review pending" },
      ]),
    );
  });

  it("binds identity, legal lifecycle, billing terms, and report identity states", () => {
    for (const name of [
      "analysis-identity-unconfirmed",
      "analysis-identity-confirmed",
      "billing-purchase-terms-expanded",
    ]) {
      expect(
        VISUAL_MATRIX_CAPTURE_SURFACES.find((surface) => surface.name === name)
          ?.profile ?? "demo",
        name,
      ).toBe("demo");
    }

    expect(
      VISUAL_MATRIX_CAPTURE_SURFACES.find(
        (surface) => surface.name === "report-review-lifecycle-transition",
      ),
    ).toMatchObject({
      expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
      profile: "api",
      sentinels: expect.arrayContaining([
        { kind: "testId", value: "report-review-lifecycle-control" },
        {
          kind: "text",
          value: "Changes Requested recorded in the governed review ledger.",
        },
        { kind: "text", value: "Visual Counsel · authoritative" },
      ]),
    });

    const summaryIdentitySentinels = [
      { kind: "heading", name: "Succinic acid" },
      { kind: "testId", value: "report-decision-memo" },
    ];
    for (const routeName of ["analysis-report", "analysis-report-summary"]) {
      expect(
        VISUAL_MATRIX_ROUTES.find((route) => route.name === routeName)
          ?.sentinels,
        routeName,
      ).toEqual(expect.arrayContaining(summaryIdentitySentinels));
    }
  });

  it("binds the P1 operational tranche to truthful API and demo profiles", () => {
    const p1Profiles = new Map(
      VISUAL_MATRIX_CAPTURE_SURFACES.slice(-26, -10).map((surface) => [
        surface.name,
        surface.profile ?? "demo",
      ]),
    );
    expect(Object.fromEntries(p1Profiles)).toEqual({
      "analyses-load-failure": "api",
      "patents-load-failure": "api",
      "compounds-load-failure": "api",
      "reviews-load-failure": "api",
      "monitors-load-failure": "api",
      "batch-load-failure": "api",
      "monitor-alert-history": "demo",
      "monitor-delete-confirm": "demo",
      "batch-detail-partial": "demo",
      "settings-sso-active": "api",
      "report-chat-success": "api",
      "report-chat-failure": "api",
      "report-comments-load-failure": "api",
      "report-watch-active": "demo",
      "billing-plan-checkout-failure": "api",
      "billing-portal-failure": "api",
    });

    const expectedFailures = Object.fromEntries(
      VISUAL_MATRIX_CAPTURE_SURFACES.slice(-26, -10)
        .filter((surface) => (surface.expectedApiFailures?.length ?? 0) > 0)
        .map((surface) => [surface.name, surface.expectedApiFailures]),
    );
    expect(expectedFailures).toEqual({
      "analyses-load-failure": ["GET /api/v1/analyses HTTP 503"],
      "patents-load-failure": ["GET /api/v1/patents HTTP 503"],
      "compounds-load-failure": ["GET /api/v1/compounds HTTP 503"],
      "reviews-load-failure": ["GET /api/v1/comments/review-queue HTTP 503"],
      "monitors-load-failure": ["GET /api/v1/monitors HTTP 503"],
      "batch-load-failure": ["GET /api/v1/batch HTTP 503"],
      "report-chat-failure": [
        `POST /api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/chat HTTP 503`,
      ],
      "report-comments-load-failure": ["GET /api/v1/comments HTTP 503"],
      "billing-plan-checkout-failure": [
        "POST /api/v1/billing/checkout HTTP 502",
      ],
      "billing-portal-failure": ["POST /api/v1/billing/portal HTTP 502"],
    });

    const expectedDiagnostics = Object.fromEntries(
      VISUAL_MATRIX_CAPTURE_SURFACES.slice(-26, -10)
        .filter(
          (surface) => (surface.expectedConsoleDiagnostics?.length ?? 0) > 0,
        )
        .map((surface) => [surface.name, surface.expectedConsoleDiagnostics]),
    );
    expect(expectedDiagnostics).toEqual({
      "patents-load-failure": [
        "error: [PatentsPage] Failed to load patent library",
      ],
      "compounds-load-failure": [
        "error: [CompoundsPage] Failed to load compound library",
      ],
      "monitors-load-failure": [
        "error: [MonitorsPage] Failed to load monitor workspace",
      ],
      "batch-load-failure": ["error: [BatchPage] APIError"],
      "report-chat-failure": ["error: [useReportChat.sendMessage] APIError"],
      "billing-plan-checkout-failure": [
        "error: [mutation] APIError",
        "error: [BillingPage] Failed to start checkout",
      ],
      "billing-portal-failure": [
        "error: [mutation] APIError",
        "error: [BillingPage] Failed to open subscription portal",
      ],
    });
  });

  it("binds the critical auth and mutation-recovery tranche to real API failures", () => {
    const recoverySurfaces = VISUAL_MATRIX_CAPTURE_SURFACES.slice(-10);
    expect(recoverySurfaces[0]).toMatchObject({
      expectedPath: "/help",
      name: "session-expired",
      path: "/help",
      sourcePage: "src/app/(dashboard)/help/page.tsx",
    });
    expect(
      Object.fromEntries(
        recoverySurfaces.map((surface) => [
          surface.name,
          surface.profile ?? "demo",
        ]),
      ),
    ).toEqual({
      "session-expired": "api",
      "report-comment-post-outcome-unknown": "api",
      "report-resolution-outcome-unknown": "api",
      "report-watch-start-outcome-unknown": "api",
      "monitor-pause-outcome-unknown": "api",
      "monitor-delete-outcome-unknown": "api",
      "monitor-alert-dismiss-outcome-unknown": "api",
      "settings-api-key-create-outcome-unknown": "api",
      "settings-api-key-revoke-outcome-unknown": "api",
      "settings-notification-save-outcome-unknown": "api",
    });

    expect(
      Object.fromEntries(
        recoverySurfaces
          .filter((surface) => (surface.expectedApiFailures?.length ?? 0) > 0)
          .map((surface) => [surface.name, surface.expectedApiFailures]),
      ),
    ).toEqual({
      "report-comment-post-outcome-unknown": ["POST /api/v1/comments HTTP 503"],
      "report-resolution-outcome-unknown": [
        `PATCH /api/v1/comments/${VISUAL_MATRIX_COMMENT_ID}/resolution HTTP 503`,
      ],
      "report-watch-start-outcome-unknown": ["POST /api/v1/monitors HTTP 503"],
      "monitor-pause-outcome-unknown": [
        `PATCH /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID} HTTP 503`,
      ],
      "monitor-delete-outcome-unknown": [
        `DELETE /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID} HTTP 503`,
      ],
      "monitor-alert-dismiss-outcome-unknown": [
        `POST /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}/alerts/${VISUAL_MATRIX_MONITOR_ALERT_ID}/dismiss HTTP 503`,
      ],
      "settings-api-key-create-outcome-unknown": [
        "POST /api/v1/api-keys HTTP 503",
      ],
      "settings-api-key-revoke-outcome-unknown": [
        `DELETE /api/v1/api-keys/${VISUAL_MATRIX_API_KEY_ID} HTTP 503`,
      ],
      "settings-notification-save-outcome-unknown": [
        "PUT /api/v1/notifications/preferences HTTP 503",
      ],
    });

    expect(
      Object.fromEntries(
        recoverySurfaces
          .filter(
            (surface) => (surface.expectedConsoleDiagnostics?.length ?? 0) > 0,
          )
          .map((surface) => [surface.name, surface.expectedConsoleDiagnostics]),
      ),
    ).toEqual({
      "report-comment-post-outcome-unknown": [
        "error: [mutation] APIError",
        "error: [CommentPanel.createComment] APIError",
      ],
      "report-resolution-outcome-unknown": [
        "error: [mutation] APIError",
        "error: [CommentPanel.resolveComment] APIError",
      ],
      "report-watch-start-outcome-unknown": [
        "error: [mutation] APIError",
        "error: [useReportWatchControl.start] APIError",
      ],
      "monitor-pause-outcome-unknown": ["error: [mutation] APIError"],
      "monitor-delete-outcome-unknown": ["error: [mutation] APIError"],
      "monitor-alert-dismiss-outcome-unknown": ["error: [mutation] APIError"],
      "settings-api-key-create-outcome-unknown": [
        "error: [mutation] APIError",
        "error: [CreateApiKeyForm] Failed to create API key",
      ],
      "settings-api-key-revoke-outcome-unknown": ["error: [mutation] APIError"],
      "settings-notification-save-outcome-unknown": [
        "error: [mutation] APIError",
      ],
    });
  });

  it("binds post-launch capture evidence to the created analysis route", () => {
    expect(
      VISUAL_MATRIX_CAPTURE_SURFACES.find(
        (surface) => surface.name === "analysis-launch-submitted",
      ),
    ).toMatchObject({
      captureExpectedPath: `/analyses/${VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID}`,
      expectedPath: "/analyses/new",
      path: "/analyses/new",
      profile: "api",
    });
  });

  it("binds API failures to production-valid identities and exact console diagnostics", () => {
    const reviewerFailure = VISUAL_MATRIX_CAPTURE_SURFACES.find(
      (surface) => surface.name === "review-decision-save-failure",
    );
    expect(reviewerFailure).toMatchObject({
      path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
      expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
      expectedApiFailures: [
        `POST /api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/decisions HTTP 503`,
      ],
    });

    for (const surface of VISUAL_MATRIX_CAPTURE_SURFACES) {
      for (const diagnostic of surface.expectedConsoleDiagnostics ?? []) {
        expect(diagnostic, surface.name).toMatch(
          /^(?:error|warning): \[[A-Za-z][A-Za-z0-9.]*\] .+/u,
        );
        expect(diagnostic, surface.name).not.toMatch(
          /\[(?:query|mutation)\]$/u,
        );
      }
    }
  });

  it("declares the two retired aliases as explicit destination surfaces", () => {
    expect(
      VISUAL_MATRIX_ROUTES.find((route) => route.name === "analyses-quick")
        ?.expectedPath,
    ).toBe("/analyses/new");
    expect(
      VISUAL_MATRIX_ROUTES.find(
        (route) => route.name === "compare-lite-agentic",
      )?.expectedPath,
    ).toBe("/compare/adaptive-agentic");
  });

  it("covers redirect-only pages without double-counting their destinations", () => {
    expect(VISUAL_MATRIX_REDIRECT_ROUTES.map((route) => route.name)).toEqual([
      "analysis-report-summary",
      "analyses-quick",
      "report-alias",
      "compare-lite-agentic",
    ]);
    expect(
      VISUAL_MATRIX_REDIRECT_ROUTES.every(
        (route) => route.path !== route.expectedPath,
      ),
    ).toBe(true);
    expect(
      VISUAL_MATRIX_CAPTURE_SURFACES.some((surface) =>
        VISUAL_MATRIX_REDIRECT_ROUTES.some(
          (redirect) => redirect.name === surface.name,
        ),
      ),
    ).toBe(false);
  });
});
