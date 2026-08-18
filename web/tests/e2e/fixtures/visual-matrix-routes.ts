export type SurfaceSentinel =
  | { kind: "heading"; name: string }
  | { kind: "testId"; value: string }
  | { kind: "text"; value: string };

export type TouchTargetException = {
  id: string;
  kind: "inline-text" | "spacing";
  rationale: string;
};

export type VisualMatrixRoute = {
  allowAppError?: boolean;
  captureExpectedPath?: string;
  captureSurface?: boolean;
  expectedPath: string;
  expectedApiFailures?: readonly string[];
  expectedConsoleDiagnostics?: readonly string[];
  name: string;
  path: string;
  profile?: "api" | "demo";
  sentinels: readonly SurfaceSentinel[];
  sourcePage: string;
  touchTargetExceptions?: readonly TouchTargetException[];
};

export const VISUAL_MATRIX_API_REPORT_ID =
  "44444444-4444-4444-8444-444444444444";
export const VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID =
  "55555555-5555-4555-8555-555555555555";
export const VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID =
  "cs_test_visualledger001";
export const VISUAL_MATRIX_MONITOR_ID = "66666666-6666-4666-8666-666666666666";
export const VISUAL_MATRIX_MONITOR_ALERT_ID =
  "77777777-7777-4777-8777-777777777776";
export const VISUAL_MATRIX_COMMENT_ID = "88888888-8888-4888-8888-888888888887";
export const VISUAL_MATRIX_API_KEY_ID = "99999999-9999-4999-8999-999999999998";
export const VISUAL_MATRIX_CLAIM_ASSERTION_ID =
  "assertion-visual-meridian-claim-1-element-1";
export const VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID =
  "span-visual-meridian-claim-1-element-1";
export const VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE =
  "Material claim mappings reviewed; request targeted source corrections before approval.";

const heading = (name: string): SurfaceSentinel => ({ kind: "heading", name });
const testId = (value: string): SurfaceSentinel => ({ kind: "testId", value });
const text = (value: string): SurfaceSentinel => ({ kind: "text", value });

/**
 * Canonical browser-visible route inventory.
 *
 * `sourcePage` is checked against every app-router `page.tsx` by a unit test.
 * Sentinels prove the intended rendered surface after the pathname settles;
 * aliases intentionally share the destination surface sentinel.
 */
export const VISUAL_MATRIX_ROUTES = [
  {
    name: "home",
    path: "/",
    expectedPath: "/",
    sourcePage: "src/app/page.tsx",
    sentinels: [
      heading("See which patent families may change your next move."),
      text("Freedom-to-operate screening for biotech"),
    ],
  },
  {
    name: "sign-in",
    path: "/sign-in",
    expectedPath: "/sign-in",
    sourcePage: "src/app/(auth)/sign-in/page.tsx",
    sentinels: [testId("sign-in-route-surface")],
  },
  {
    name: "sign-in-sso-callback",
    path: "/sign-in/sso-callback",
    expectedPath: "/sign-in/sso-callback",
    sourcePage: "src/app/(auth)/sign-in/sso-callback/page.tsx",
    sentinels: [testId("sign-in-sso-callback-route-surface")],
  },
  {
    name: "sign-up",
    path: "/sign-up",
    expectedPath: "/sign-up",
    sourcePage: "src/app/(auth)/sign-up/page.tsx",
    sentinels: [testId("sign-up-route-surface")],
  },
  {
    name: "sign-up-sso-callback",
    path: "/sign-up/sso-callback",
    expectedPath: "/sign-up/sso-callback",
    sourcePage: "src/app/(auth)/sign-up/sso-callback/page.tsx",
    sentinels: [testId("sign-up-sso-callback-route-surface")],
  },
  {
    name: "admin-analytics",
    path: "/admin/analytics",
    expectedPath: "/admin/analytics",
    sourcePage: "src/app/(dashboard)/admin/analytics/page.tsx",
    sentinels: [
      heading("Cost & Usage"),
      testId("admin-analytics-app-surface-header"),
    ],
  },
  {
    name: "admin",
    path: "/admin",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [heading("Platform Admin"), testId("admin-app-surface-header")],
  },
  {
    name: "analysis-detail",
    path: "/analyses/ana_demo_001",
    expectedPath: "/analyses/ana_demo_001",
    sourcePage: "src/app/(dashboard)/analyses/[id]/page.tsx",
    sentinels: [heading("Succinic acid"), text("ID: ana_demo_001")],
  },
  {
    name: "analysis-report",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [heading("Succinic acid"), testId("report-decision-memo")],
  },
  {
    name: "analysis-report-summary",
    path: "/analyses/ana_demo_001/report/summary",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/summary/page.tsx",
    captureSurface: false,
    sentinels: [heading("Succinic acid"), testId("report-decision-memo")],
  },
  {
    name: "analysis-new",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    sentinels: [heading("New FTO Analysis"), text("Compound-first workflow")],
  },
  {
    name: "analyses",
    path: "/analyses",
    expectedPath: "/analyses",
    sourcePage: "src/app/(dashboard)/analyses/page.tsx",
    sentinels: [
      heading("Analysis Library"),
      testId("analyses-app-surface-header"),
    ],
  },
  {
    name: "analyses-quick",
    path: "/analyses/quick",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/quick/page.tsx",
    captureSurface: false,
    sentinels: [heading("New FTO Analysis"), text("Compound-first workflow")],
  },
  {
    name: "batch",
    path: "/batch",
    expectedPath: "/batch",
    sourcePage: "src/app/(dashboard)/batch/page.tsx",
    sentinels: [
      heading("Diligence portfolio workspace"),
      testId("batch-app-surface-header"),
    ],
  },
  {
    name: "billing",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    sentinels: [
      heading("Credits & Billing"),
      testId("billing-app-surface-header"),
    ],
  },
  {
    name: "capabilities",
    path: "/capabilities",
    expectedPath: "/capabilities",
    sourcePage: "src/app/(dashboard)/capabilities/page.tsx",
    sentinels: [
      heading("FTO Workflow Atlas"),
      testId("capabilities-app-surface-header"),
    ],
  },
  {
    name: "compounds",
    path: "/compounds",
    expectedPath: "/compounds",
    sourcePage: "src/app/(dashboard)/compounds/page.tsx",
    sentinels: [
      heading("Compound Library"),
      testId("compounds-app-surface-header"),
    ],
  },
  {
    name: "config",
    path: "/config",
    expectedPath: "/config",
    sourcePage: "src/app/(dashboard)/config/page.tsx",
    sentinels: [heading("Configuration"), testId("config-app-surface-header")],
  },
  {
    name: "dashboard",
    path: "/dashboard",
    expectedPath: "/dashboard",
    sourcePage: "src/app/(dashboard)/dashboard/page.tsx",
    sentinels: [heading("Dashboard"), testId("dashboard-app-surface-header")],
  },
  {
    name: "help",
    path: "/help",
    expectedPath: "/help",
    sourcePage: "src/app/(dashboard)/help/page.tsx",
    sentinels: [
      heading("Help & Documentation"),
      testId("help-app-surface-header"),
    ],
  },
  {
    name: "monitors",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    sentinels: [
      heading("Patent monitoring workspace"),
      testId("monitors-app-surface-header"),
    ],
  },
  {
    name: "patents",
    path: "/patents",
    expectedPath: "/patents",
    sourcePage: "src/app/(dashboard)/patents/page.tsx",
    sentinels: [
      heading("Patent Evidence Library"),
      testId("patents-app-surface-header"),
    ],
  },
  {
    name: "report-alias",
    path: "/reports/rpt_ana_demo_001",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/reports/[id]/page.tsx",
    captureSurface: false,
    sentinels: [heading("Succinic acid"), testId("report-decision-memo")],
  },
  {
    name: "reviews",
    path: "/reviews",
    expectedPath: "/reviews",
    sourcePage: "src/app/(dashboard)/reviews/page.tsx",
    sentinels: [
      heading("Legal Review Queue"),
      testId("review-queue-app-surface-header"),
    ],
  },
  {
    name: "settings-notifications",
    path: "/settings/notifications",
    expectedPath: "/settings/notifications",
    sourcePage: "src/app/(dashboard)/settings/notifications/page.tsx",
    sentinels: [
      heading("Notification settings"),
      testId("notification-settings-app-surface-header"),
    ],
  },
  {
    name: "settings",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    sentinels: [heading("Settings"), testId("settings-app-surface-header")],
  },
  {
    name: "compare-adaptive-agentic",
    path: "/compare/adaptive-agentic",
    expectedPath: "/compare/adaptive-agentic",
    sourcePage: "src/app/(marketing)/compare/adaptive-agentic/page.tsx",
    sentinels: [
      heading("One evidence path that deepens when the record demands it."),
    ],
  },
  {
    name: "compare-lite-agentic",
    path: "/compare/lite-vs-agentic",
    expectedPath: "/compare/adaptive-agentic",
    sourcePage: "src/app/(marketing)/compare/lite-vs-agentic/page.tsx",
    captureSurface: false,
    sentinels: [
      heading("One evidence path that deepens when the record demands it."),
    ],
  },
  {
    name: "demo",
    path: "/demo",
    expectedPath: "/demo",
    sourcePage: "src/app/(marketing)/demo/page.tsx",
    sentinels: [
      heading("Inspect a first-pass FTO dossier before you run one."),
    ],
  },
  {
    name: "biotech-founders",
    path: "/for-biotech-founders",
    expectedPath: "/for-biotech-founders",
    sourcePage: "src/app/(marketing)/for-biotech-founders/page.tsx",
    sentinels: [
      heading("Know the patent risk before the next financing milestone"),
    ],
  },
  {
    name: "methodology",
    path: "/methodology",
    expectedPath: "/methodology",
    sourcePage: "src/app/(marketing)/methodology/page.tsx",
    sentinels: [
      heading("A first-pass FTO workflow that makes evidence inspectable."),
    ],
  },
  {
    name: "privacy",
    path: "/privacy",
    expectedPath: "/privacy",
    sourcePage: "src/app/(marketing)/privacy/page.tsx",
    sentinels: [
      heading("Research Preview Privacy Notice"),
      testId("legal-document"),
    ],
  },
  {
    name: "sample-report",
    path: "/sample-reports/example-molecule-alpha",
    expectedPath: "/sample-reports/example-molecule-alpha",
    sourcePage: "src/app/(marketing)/sample-reports/[slug]/page.tsx",
    sentinels: [
      heading("Example Molecule Alpha"),
      testId("fto-dossier-preview"),
    ],
  },
  {
    name: "sample-reports",
    path: "/sample-reports",
    expectedPath: "/sample-reports",
    sourcePage: "src/app/(marketing)/sample-reports/page.tsx",
    sentinels: [
      heading("See the report before you run one."),
      testId("sample-report-anatomy"),
    ],
  },
  {
    name: "terms",
    path: "/terms",
    expectedPath: "/terms",
    sourcePage: "src/app/(marketing)/terms/page.tsx",
    sentinels: [
      heading("Research Preview Use Notice"),
      testId("legal-document"),
    ],
  },
  {
    name: "trust",
    path: "/trust",
    expectedPath: "/trust",
    sourcePage: "src/app/(marketing)/trust/page.tsx",
    sentinels: [
      heading("Know what Praviar can protect and prove before you use it."),
      testId("trust-control-visual"),
    ],
  },
  {
    name: "digest-unsubscribe",
    path: `/unsubscribe/digest?token=${"t".repeat(80)}`,
    expectedPath: "/unsubscribe/digest",
    sourcePage: "src/app/unsubscribe/digest/page.tsx",
    sentinels: [
      heading("Stop weekly digest emails?"),
      text("Turn off weekly digests"),
    ],
  },
  {
    name: "share",
    path: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    expectedPath: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    sourcePage: "src/app/share/[token]/page.tsx",
    sentinels: [
      heading("Verify intended recipient"),
      text("External shared FTO packet"),
    ],
  },
] as const satisfies readonly VisualMatrixRoute[];

/**
 * Redirect-only pages remain in `VISUAL_MATRIX_ROUTES` so every App Router
 * page is exercised, but they do not inflate the independently scored visual
 * inventory with a byte-identical destination capture.
 */
export const VISUAL_MATRIX_CAPTURE_ROUTES = VISUAL_MATRIX_ROUTES.filter(
  (route) => route.captureSurface !== false,
);

export const VISUAL_MATRIX_REDIRECT_ROUTES = VISUAL_MATRIX_ROUTES.filter(
  (route) => route.captureSurface === false,
);

/**
 * Browser-visible states retained by the evidence run. Interaction states at
 * an existing URL are deliberately separate named surfaces: each must be
 * reached through the buyer action in the browser and receives its own PNG,
 * record, hash, and receipt identity.
 */
export const VISUAL_MATRIX_CAPTURE_SURFACES = [
  ...VISUAL_MATRIX_CAPTURE_ROUTES,
  ...(
    [
      "patents",
      "claims",
      "evidence",
      "invalidity",
      "comments",
      "drawings",
      "regulatory",
      "audit",
      "meta",
      "reasoning",
    ] as const
  ).map((tab) => ({
    name: `report-tab-${tab}`,
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [testId(`report-tab-${tab}`)],
  })),
  {
    name: "share-verified",
    path: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    expectedPath: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    sourcePage: "src/app/share/[token]/page.tsx",
    sentinels: [heading("Succinic acid"), text("Attributable verified view")],
  },
  {
    name: "sender-share-success",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Invitation accepted for delivery to visual.counsel@example.com"),
      text("Named access history"),
    ],
  },
  {
    name: "share-activity-expanded",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Delivery provider accepted invitation"),
      text("Report view 2"),
      text("2026-07-13T09:30:00Z UTC"),
    ],
  },
  {
    name: "share-revoke-confirm",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [text("Revoke this recipient?")],
  },
  {
    name: "approved-domains-policy",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    sentinels: [
      text("Confirm destructive policy enforcement"),
      text("Confirm and enforce policy"),
    ],
  },
  {
    name: "analysis-launch-review",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    sentinels: [text("Confirm & Launch"), testId("review-launch-source-card")],
  },
  {
    name: "analysis-identity-unconfirmed",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    sentinels: [
      testId("compound-identity-decision-sheet"),
      testId("compound-identity-confirmation-status"),
      text("Submitted input → resolved search identity"),
      text("Review before continuing"),
      text("Pending authoritative resolution"),
      text("Confirm for resolution"),
      text("Next: Configure"),
    ],
  },
  {
    name: "analysis-identity-confirmed",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    sentinels: [
      testId("compound-identity-decision-sheet"),
      testId("compound-identity-confirmation-status"),
      text("Submitted input → resolved search identity"),
      text("Confirmed for resolution"),
      text("Submitted identity confirmed"),
      text("Next: Configure"),
    ],
  },
  {
    name: "analysis-launch-submitted",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    captureExpectedPath: `/analyses/${VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID}`,
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    profile: "api",
    sentinels: [
      heading("Succinic acid"),
      text(`ID: ${VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID}`),
      text("Pipeline queued"),
    ],
  },
  {
    name: "first-run-welcome",
    path: "/dashboard",
    expectedPath: "/dashboard",
    sourcePage: "src/app/(dashboard)/dashboard/page.tsx",
    sentinels: [text("Step 1 of 3"), testId("welcome-packet-preview")],
  },
  {
    name: "billing-credit-intent",
    path: "/billing?intent=credits&pack=portfolio_5&needed_reports=5&source=launch&return_to=%2Fanalyses%2Fnew",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    sentinels: [
      testId("billing-credit-intent-hero"),
      testId("billing-credit-intent-terms"),
    ],
  },
  {
    name: "billing-purchase-terms-expanded",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    sentinels: [
      testId("credit-pack-checkout-terms"),
      text("Purchase terms and legal boundary"),
      text("One-time Report Credit Pack"),
      text("Hosted checkout · no card storage"),
      text("Receipt + ledger"),
      text("First-pass request"),
      text(
        "Report Credits start source-linked first-pass workflows for counsel review, not legal conclusions.",
      ),
    ],
  },
  {
    name: "command-palette",
    path: "/dashboard",
    expectedPath: "/dashboard",
    sourcePage: "src/app/(dashboard)/dashboard/page.tsx",
    sentinels: [text("Recent Analyses"), text("Actions")],
  },
  {
    name: "dashboard-ai-actions-expanded",
    path: "/dashboard",
    expectedPath: "/dashboard",
    sourcePage: "src/app/(dashboard)/dashboard/page.tsx",
    sentinels: [
      testId("dashboard-ai-command-disclosure"),
      testId("dashboard-ai-command-panel"),
      text("Evidence-ready next moves"),
      text("Claim-cited output"),
      text("Human review gate"),
      text("Tenant-scoped context"),
    ],
  },
  {
    name: "monitor-create",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    sentinels: [text("Create New Monitor"), text("Monitoring setup")],
  },
  {
    name: "batch-create",
    path: "/batch",
    expectedPath: "/batch",
    sourcePage: "src/app/(dashboard)/batch/page.tsx",
    sentinels: [text("Create Batch Analysis"), text("0 compounds entered")],
  },
  {
    name: "blocked-export-recovery",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      testId("report-export-recovery-brief"),
      text("Resolve export blockers before evidence leaves Praviar"),
    ],
  },
  {
    name: "report-export-ready",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    sentinels: [
      text("Evidence packet ready"),
      text("Download verified packet"),
      text("Export ready"),
    ],
  },
  {
    name: "batch-cancel-confirm",
    path: "/batch",
    expectedPath: "/batch",
    sourcePage: "src/app/(dashboard)/batch/page.tsx",
    sentinels: [text("Cancel batch run?"), text("Batch under review")],
  },
  {
    name: "review-bulk-confirm",
    path: "/reviews",
    expectedPath: "/reviews",
    sourcePage: "src/app/(dashboard)/reviews/page.tsx",
    sentinels: [text("Confirm thread resolution"), text("Selected threads")],
  },
  {
    name: "admin-clerk-operation-unconfirmed",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    profile: "api",
    sentinels: [
      text("Invitation to visual.buyer@example.com: unconfirmed"),
      text("Reconcile now"),
    ],
  },
  {
    name: "admin-clerk-operation-reconciled",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    profile: "api",
    sentinels: [
      text("Invitation to visual.buyer@example.com: reconciled"),
      text("Provider and Praviar authority are reconciled and confirmed."),
    ],
  },
  {
    name: "admin-clerk-operation-rejected",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    profile: "api",
    sentinels: [
      text("Invitation to visual.buyer@example.com: failed"),
      text(
        "The operation was rejected and was not applied. A new submission will create a new operation.",
      ),
    ],
  },
  {
    name: "admin-clerk-authority-unsynchronized",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    profile: "api",
    sentinels: [
      text("Clerk authority reconciliation required"),
      text("Recheck authority"),
      text("Reconciliation required"),
    ],
  },
  {
    name: "share-delivery-outcome-unknown",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Delivery outcome unknown"),
      text("Cancel unresolved invitation"),
    ],
  },
  {
    name: "share-delivery-outcome-cancel-confirm",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [text("Cancel this unresolved invitation?")],
  },
  {
    name: "share-delivery-refresh-resolved",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [text("Active invitation")],
  },
  {
    name: "share-delivery-reconciliation-alert",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Operator review required"),
      text("Delivery reconciliation requires operator review."),
    ],
  },
  {
    name: "share-delivery-cancelled-retention",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Cancelled after retention"),
      text("Cancelled when provider lookup retention ended."),
      text("Start new invitation attempt"),
    ],
  },
  {
    name: "external-share-link-unavailable",
    path: "/share/sg_visual_unavailable_7Kp2mQ9xV4cN8rT6wH3z",
    expectedPath: "/share/sg_visual_unavailable_7Kp2mQ9xV4cN8rT6wH3z",
    sourcePage: "src/app/share/[token]/page.tsx",
    allowAppError: true,
    sentinels: [heading("Report not available"), text("Link unavailable")],
  },
  {
    name: "external-share-verification-error",
    path: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    expectedPath: "/share/sg_demo_mailbox_grant_7Kp2mQ9xV4cN8rT6wH3z",
    sourcePage: "src/app/share/[token]/page.tsx",
    sentinels: [text("That code is invalid, expired, or already used.")],
  },
  {
    name: "billing-credit-checkout-return-reconciling",
    path: `/billing?checkout=success&credit_pack=portfolio_5&intent=credits&return_to=%2Fanalyses%2Fnew&checkout_session_id=${VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID}`,
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    sentinels: [
      testId("credit-reconciliation-pending"),
      text("Checkout returned; Report Credits pending"),
      text("Awaiting ledger confirmation"),
    ],
  },
  {
    name: "billing-credit-ledger-reconciled",
    path: `/billing?checkout=success&credit_pack=portfolio_5&intent=credits&return_to=%2Fanalyses%2Fnew&checkout_session_id=${VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID}`,
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    sentinels: [
      testId("credit-reconciliation-applied"),
      text("Organization ledger confirmed"),
      text("5 Report Credits applied"),
      text("7 Report Credits"),
    ],
  },
  {
    name: "billing-credit-checkout-cancelled",
    path: "/billing?checkout=cancelled&credit_pack=portfolio_5&intent=credits&return_to=%2Fanalyses%2Fnew",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    sentinels: [
      text("Checkout flow cancelled"),
      text(
        "No billing or Report Credit changes are assumed from this browser return. Authoritative balances remain visible below.",
      ),
    ],
  },
  {
    name: "billing-credit-checkout-failure",
    path: "/billing?intent=credits&pack=single_analysis",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    expectedApiFailures: [
      "POST /api/v1/billing/credit-packs/checkout HTTP 502",
    ],
    expectedConsoleDiagnostics: [
      "error: [BillingPage] Failed to start credit checkout",
      "error: [mutation] APIError",
    ],
    sentinels: [
      testId("billing-action-error-notice"),
      text("Checkout not started"),
      text("Retry checkout"),
    ],
  },
  {
    name: "auth-checkout-intent-signed-out",
    path: "/sign-in?return_to=%2Fbilling%3Fintent%3Dcredits%26needed_reports%3D5%26pack%3Dportfolio_5",
    expectedPath: "/sign-in",
    sourcePage: "src/app/(auth)/sign-in/page.tsx",
    sentinels: [
      testId("auth-checkout-intent"),
      text("Selected before sign-in"),
    ],
  },
  {
    name: "admin-users-invite",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("Email Address"), text("Send Invite")],
  },
  {
    name: "admin-organizations",
    path: "/admin",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("Praviar Demo Biotech"), text("Northstar Therapeutics")],
  },
  {
    name: "admin-ops-snapshot",
    path: "/admin",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("Total Analyses"), text("Daily Activity")],
  },
  {
    name: "admin-audit-logs",
    path: "/admin",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("report.export.queued"), text("ada@example.com")],
  },
  {
    name: "admin-tasks",
    path: "/admin",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("Running Tasks (1)"), text("Reserved Tasks (1)")],
  },
  {
    name: "admin-users-role-review",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    sentinels: [text("Review role change")],
  },
  {
    name: "admin-users-restricted",
    path: "/admin?tab=users",
    expectedPath: "/admin",
    sourcePage: "src/app/(dashboard)/admin/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/admin/users HTTP 403"],
    expectedConsoleDiagnostics: [
      "error: [UsersTab] User controls access restricted",
    ],
    sentinels: [
      testId("admin-users-status-restricted"),
      text("User controls access restricted"),
      text("Retry admin load"),
    ],
  },
  {
    name: "billing-actions-restricted",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    sentinels: [
      testId("billing-action-access-notice"),
      text("Billing purchase controls require admin access"),
      text("Review support boundary"),
    ],
  },
  {
    name: "billing-stale-data",
    path: "/billing?checkout=success&credit_pack=portfolio_5",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    expectedApiFailures: ["GET /api/v1/billing/status HTTP 503"],
    expectedConsoleDiagnostics: ["error: [query] APIError"],
    sentinels: [
      testId("billing-stale-data-notice"),
      text(
        "Billing refresh failed. Existing subscription and usage data is still shown, and no plan or payment changes were made.",
      ),
      testId("billing-stale-data-age"),
      text("Retry billing data"),
    ],
  },
  {
    name: "billing-invoice-unavailable",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    expectedApiFailures: ["GET /api/v1/billing/invoices HTTP 503"],
    sentinels: [
      testId("billing-invoice-status-notice"),
      text("Invoice history temporarily unavailable"),
      text("Retry invoice history"),
    ],
  },
  {
    name: "analysis-capacity-blocked",
    path: "/analyses/new",
    expectedPath: "/analyses/new",
    sourcePage: "src/app/(dashboard)/analyses/new/page.tsx",
    profile: "api",
    sentinels: [
      testId("capacity-credit-action"),
      text(
        "No FTO report request capacity remains. Buy Report Credits or wait for the next billing period before starting another request.",
      ),
      text("Buy 1 Report Credit"),
    ],
  },
  {
    name: "analysis-running",
    path: "/analyses/ana_demo_002",
    expectedPath: "/analyses/ana_demo_002",
    sourcePage: "src/app/(dashboard)/analyses/[id]/page.tsx",
    sentinels: [
      testId("live-evidence-dossier"),
      text("Audit trail in progress"),
    ],
  },
  {
    name: "analysis-failed",
    path: "/analyses/ana_visual_failed",
    expectedPath: "/analyses/ana_visual_failed",
    sourcePage: "src/app/(dashboard)/analyses/[id]/page.tsx",
    sentinels: [
      text("Analysis failed"),
      text("Evidence preserved"),
      text("Start replacement analysis"),
    ],
  },
  {
    name: "analyses-empty",
    path: "/analyses?q=zzz_nonexistent_compound",
    expectedPath: "/analyses",
    sourcePage: "src/app/(dashboard)/analyses/page.tsx",
    sentinels: [text("No analyses match your filters"), text("Clear filters")],
  },
  {
    name: "report-patent-detail-open",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("US0000000001A1"),
      text("Google Patents"),
      text("Legal Status & Term"),
    ],
  },
  {
    name: "report-citation-source-open",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [text("Cited Passage"), text("US0000000001A1"), text("Claim 1")],
  },
  {
    name: "report-claim-decision-source-review",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    sentinels: [
      testId("claim-decision-matrix"),
      testId(`claim-exact-source-${VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID}`),
      text("1 · Source fact"),
      text("Inspect provenance receipt"),
      text("2 · AI-assisted inference"),
      text("3 · Human decision"),
      text("Review pending"),
    ],
  },
  {
    name: "review-decision-save-failure",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `POST /api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/decisions HTTP 503`,
    ],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [useCreateReviewerDecision] APIError",
    ],
    sentinels: [
      text(
        "Save outcome unknown. The server may have recorded this decision. Check the reviewer ledger before retrying.",
      ),
    ],
  },
  {
    name: "report-review-decision-saved",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    sentinels: [
      text("1 / 3 findings reviewed"),
      text("Rejected · 1 reviewer"),
      text("1/2 reviews"),
    ],
  },
  {
    name: "report-review-lifecycle-transition",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    sentinels: [
      testId("report-review-lifecycle-control"),
      text("Changes Requested recorded in the governed review ledger."),
      text("Visual Counsel · authoritative"),
      text("0 / 3 reviewed"),
    ],
  },
  {
    name: "report-coverage-recovery",
    path: "/analyses/ana_demo_001/report?tab=meta",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [
      text("Analysis Failures"),
      text("Report is screening-only until gaps are reviewed"),
      text("Data Limitations"),
    ],
  },
  {
    name: "settings-api-key-reveal",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    sentinels: [text("API key created")],
  },
  {
    name: "settings-api-key-revoke-confirm",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    sentinels: [text("Production case workspace API")],
  },
  {
    name: "settings-sso-config-failure",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/admin/sso/configure HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [SSOSettings] Failed to update SSO configuration",
      "error: [mutation] APIError",
    ],
    sentinels: [
      testId("sso-configuration-error"),
      text("SSO change outcome unknown"),
      text("Check SSO status"),
    ],
  },
  {
    name: "analyses-load-failure",
    path: "/analyses",
    expectedPath: "/analyses",
    sourcePage: "src/app/(dashboard)/analyses/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/analyses HTTP 503"],
    sentinels: [
      text("Analysis library temporarily unavailable"),
      text(
        "We could not load the library index right now. Existing reports are preserved; retry when the workspace connection is available.",
      ),
      text("Retry"),
    ],
  },
  {
    name: "patents-load-failure",
    path: "/patents",
    expectedPath: "/patents",
    sourcePage: "src/app/(dashboard)/patents/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/patents HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [PatentsPage] Failed to load patent library",
    ],
    sentinels: [
      testId("patents-library-status-temporary"),
      text("Patent evidence library temporarily unavailable"),
      text("Retry library load"),
    ],
  },
  {
    name: "compounds-load-failure",
    path: "/compounds",
    expectedPath: "/compounds",
    sourcePage: "src/app/(dashboard)/compounds/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/compounds HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [CompoundsPage] Failed to load compound library",
    ],
    sentinels: [
      testId("compounds-library-status-temporary"),
      text("Compound library temporarily unavailable"),
      text("Retry library load"),
    ],
  },
  {
    name: "reviews-load-failure",
    path: "/reviews",
    expectedPath: "/reviews",
    sourcePage: "src/app/(dashboard)/reviews/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/comments/review-queue HTTP 503"],
    sentinels: [
      testId("review-queue-temporary"),
      text("Review queue temporarily unavailable."),
      text("Retry"),
    ],
  },
  {
    name: "monitors-load-failure",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/monitors HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [MonitorsPage] Failed to load monitor workspace",
    ],
    sentinels: [
      testId("monitors-workspace-status-temporary"),
      text("Patent monitoring temporarily unavailable"),
      text("Retry workspace load"),
    ],
  },
  {
    name: "batch-load-failure",
    path: "/batch",
    expectedPath: "/batch",
    sourcePage: "src/app/(dashboard)/batch/page.tsx",
    profile: "api",
    allowAppError: true,
    expectedApiFailures: ["GET /api/v1/batch HTTP 503"],
    expectedConsoleDiagnostics: ["error: [BatchPage] APIError"],
    sentinels: [
      testId("batch-workspace-status-temporary"),
      text("Diligence portfolio temporarily unavailable"),
      text("Retry workspace load"),
    ],
  },
  {
    name: "monitor-alert-history",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    sentinels: [
      text("Alert history"),
      text("Succinic acid watch"),
      text(
        "1 new continuation in succinic-acid manufacturing claims surfaced overnight.",
      ),
      text("Mark reviewed"),
    ],
  },
  {
    name: "monitor-delete-confirm",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    sentinels: [
      text("Delete monitor and stop scheduled checks?"),
      text(
        "Succinic acid watch will stop future monitoring runs. Existing reports remain unchanged; retained audit records stay available according to workspace policy.",
      ),
      text("Delete monitor"),
    ],
  },
  {
    name: "batch-detail-partial",
    path: "/batch",
    expectedPath: "/batch",
    sourcePage: "src/app/(dashboard)/batch/page.tsx",
    sentinels: [
      text("Platform acid portfolio"),
      text("batch_demo_002"),
      text("100% complete"),
      text("Available analysis packets"),
    ],
  },
  {
    name: "settings-sso-active",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    profile: "api",
    sentinels: [
      text("Active"),
      text("Okta Workforce Identity"),
      text("praviar-visual.example.com"),
      text("Start disable request"),
    ],
  },
  {
    name: "report-chat-success",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    sentinels: [
      text("Which patents pose the highest risk?"),
      text(
        "US0000000001A1 is the lead high-risk family because claim 1 maps directly to the evaluated succinic-acid process. Verify the cited claim language before relying on this screening result.",
      ),
    ],
  },
  {
    name: "report-chat-failure",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `POST /api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/chat HTTP 503`,
    ],
    expectedConsoleDiagnostics: ["error: [useReportChat.sendMessage] APIError"],
    sentinels: [
      text("Which patents pose the highest risk?"),
      text(
        "Chat response could not be completed. Existing report evidence is unchanged.",
      ),
    ],
  },
  {
    name: "report-comments-load-failure",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: ["GET /api/v1/comments HTTP 503"],
    sentinels: [
      testId("comment-panel-load-error"),
      text("Comments temporarily unavailable"),
      text("Retry comments load"),
    ],
  },
  {
    name: "report-watch-active",
    path: "/analyses/ana_demo_001/report",
    expectedPath: "/analyses/ana_demo_001/report",
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    sentinels: [text("Watching"), text("Active")],
  },
  {
    name: "billing-plan-checkout-failure",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/billing/checkout HTTP 502"],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [BillingPage] Failed to start checkout",
    ],
    sentinels: [
      testId("billing-action-error-notice"),
      text("Plan checkout did not start"),
      text("Retry plan checkout"),
    ],
  },
  {
    name: "billing-portal-failure",
    path: "/billing",
    expectedPath: "/billing",
    sourcePage: "src/app/(dashboard)/billing/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/billing/portal HTTP 502"],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [BillingPage] Failed to open subscription portal",
    ],
    sentinels: [
      testId("billing-action-error-notice"),
      text("Subscription portal did not open"),
      text("Retry billing portal"),
    ],
  },
  {
    name: "session-expired",
    path: "/help",
    expectedPath: "/help",
    sourcePage: "src/app/(dashboard)/help/page.tsx",
    profile: "api",
    sentinels: [
      testId("session-recovery-banner"),
      text("Your session expired"),
      text(
        "Private workspace actions are locked. Existing analyses, reports, monitors, review decisions, and account settings are unchanged.",
      ),
      text("Retry session"),
      text("Sign in again"),
    ],
  },
  {
    name: "report-comment-post-outcome-unknown",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/comments HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [CommentPanel.createComment] APIError",
    ],
    sentinels: [
      testId("comment-post-recovery"),
      text("Comment outcome unconfirmed"),
      text("Refresh discussion"),
      text(
        "Confirm the independent-claim mapping before the report is used for launch clearance.",
      ),
    ],
  },
  {
    name: "report-resolution-outcome-unknown",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `PATCH /api/v1/comments/${VISUAL_MATRIX_COMMENT_ID}/resolution HTTP 503`,
    ],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [CommentPanel.resolveComment] APIError",
    ],
    sentinels: [
      testId(`comment-resolution-recovery-${VISUAL_MATRIX_COMMENT_ID}`),
      text("Resolution outcome unconfirmed"),
      text("Refresh discussion"),
      text(
        "Confirm the independent-claim mapping before the report is used for launch clearance.",
      ),
    ],
  },
  {
    name: "report-watch-start-outcome-unknown",
    path: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    expectedPath: `/analyses/${VISUAL_MATRIX_API_REPORT_ID}/report`,
    sourcePage: "src/app/(dashboard)/analyses/[id]/report/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/monitors HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [useReportWatchControl.start] APIError",
    ],
    sentinels: [testId("report-watch-recovery-dialog")],
  },
  {
    name: "monitor-pause-outcome-unknown",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `PATCH /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID} HTTP 503`,
    ],
    expectedConsoleDiagnostics: ["error: [mutation] APIError"],
    sentinels: [
      testId("monitor-update-recovery"),
      text("Monitor update outcome unconfirmed"),
      text("Reapply pause"),
      text("Visual process watch"),
    ],
  },
  {
    name: "monitor-delete-outcome-unknown",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `DELETE /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID} HTTP 503`,
    ],
    expectedConsoleDiagnostics: ["error: [mutation] APIError"],
    sentinels: [
      testId("monitor-delete-recovery"),
      text("Monitor deletion outcome unconfirmed"),
      text("Refresh monitor workspace"),
      text("Visual process watch"),
    ],
  },
  {
    name: "monitor-alert-dismiss-outcome-unknown",
    path: "/monitors",
    expectedPath: "/monitors",
    sourcePage: "src/app/(dashboard)/monitors/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `POST /api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}/alerts/${VISUAL_MATRIX_MONITOR_ALERT_ID}/dismiss HTTP 503`,
    ],
    expectedConsoleDiagnostics: ["error: [mutation] APIError"],
    sentinels: [
      testId("monitor-alert-dismiss-recovery"),
      text("Alert dismissal outcome unconfirmed"),
      text("Retry exact dismissal"),
      text("Alert history"),
      text("Visual process watch"),
    ],
  },
  {
    name: "settings-api-key-create-outcome-unknown",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    profile: "api",
    expectedApiFailures: ["POST /api/v1/api-keys HTTP 503"],
    expectedConsoleDiagnostics: [
      "error: [mutation] APIError",
      "error: [CreateApiKeyForm] Failed to create API key",
    ],
    sentinels: [
      testId("api-key-create-recovery"),
      text("API key creation outcome unconfirmed"),
      text("Refresh API key ledger"),
      text("Create new API key"),
    ],
  },
  {
    name: "settings-api-key-revoke-outcome-unknown",
    path: "/settings",
    expectedPath: "/settings",
    sourcePage: "src/app/(dashboard)/settings/page.tsx",
    profile: "api",
    expectedApiFailures: [
      `DELETE /api/v1/api-keys/${VISUAL_MATRIX_API_KEY_ID} HTTP 503`,
    ],
    expectedConsoleDiagnostics: ["error: [mutation] APIError"],
    sentinels: [
      testId("api-key-revoke-recovery"),
      text("API key revocation outcome unconfirmed"),
      text("Refresh API key ledger"),
      text("Visual pipeline key"),
    ],
  },
  {
    name: "settings-notification-save-outcome-unknown",
    path: "/settings/notifications",
    expectedPath: "/settings/notifications",
    sourcePage: "src/app/(dashboard)/settings/notifications/page.tsx",
    profile: "api",
    expectedApiFailures: ["PUT /api/v1/notifications/preferences HTTP 503"],
    expectedConsoleDiagnostics: ["error: [mutation] APIError"],
    sentinels: [
      testId("notification-preferences-save-recovery"),
      text("Notification save outcome unconfirmed"),
      text("Reapply exact preferences"),
      heading("Notification settings"),
    ],
  },
] as const satisfies readonly VisualMatrixRoute[];

export function visualMatrixSurfacesForProfile(profile: "api" | "demo") {
  return VISUAL_MATRIX_CAPTURE_SURFACES.filter(
    (surface) => (surface.profile ?? "demo") === profile,
  );
}
