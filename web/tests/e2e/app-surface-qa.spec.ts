import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./fixtures/strict-test";
import {
  DEMO_ONBOARDING_IDENTITY,
  onboardingStorageKeys,
} from "../../src/lib/onboarding-storage";

const VIEWPORTS = [
  { name: "320px", width: 320, height: 812 },
  { name: "375px", width: 375, height: 812 },
  { name: "768px", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
] as const;

const DEMO_FIXTURES_ENABLED = process.env.PLAYWRIGHT_DEMO_MODE === "true";

const APP_ROUTES = [
  {
    path: "/dashboard",
    heading: "Dashboard",
    proofText: "Patent intelligence workspace",
  },
  {
    path: "/analyses",
    heading: "Analysis Library",
    proofText: "Search and filter packets",
  },
  {
    path: "/analyses/new",
    heading: "New FTO Analysis",
    proofText: "Compound-first workflow",
  },
  {
    path: "/compounds",
    heading: "Compound Library",
    proofText: "Succinic acid",
  },
  {
    path: "/patents",
    heading: "Patent Evidence Library",
    proofText: "Evidence readiness",
  },
  {
    path: "/reviews",
    heading: "Legal Review Queue",
    proofText: "Open ownership handoffs",
  },
  {
    path: "/monitors",
    heading: "Patent monitoring workspace",
    proofText: "Scope watch",
  },
  {
    path: "/batch",
    heading: "Diligence portfolio workspace",
    proofText: "Portfolio runs",
  },
  {
    path: "/billing",
    heading: "Credits & Billing",
    proofText: "Prepaid Report Credit capacity",
  },
  {
    path: "/settings",
    heading: "Settings",
    proofText: "Access & Automation",
  },
  {
    path: "/config",
    heading: "Configuration",
    proofText: "Organization-wide default coverage",
  },
  {
    path: "/help",
    heading: "Help & Documentation",
    proofText: "Start from the workflow, not the manual",
  },
  {
    path: "/capabilities",
    heading: "FTO Workflow Atlas",
    proofText: "Start with the user question",
  },
  {
    path: "/admin",
    heading: "Platform Admin",
    proofText: "System health",
  },
  {
    path: "/admin/analytics",
    heading: "Cost & Usage",
    proofText: "Track administrator-scoped",
  },
] as const;

const AUTH_ROUTES = [
  {
    path: "/sign-in",
    heading: "Sign In",
  },
  {
    path: "/sign-up",
    heading: "Sign Up",
  },
] as const;

type AppSurfaceSsoStatus = {
  sso_enabled: boolean;
  provider: string | null;
  domains: string[];
  status: "active" | "pending" | "inactive";
  clerk_dashboard_url: string | null;
  sso_status_available: boolean;
  sso_last_synced_at: string | null;
  sso_status_stale: boolean;
  sso_unavailable_reason:
    | "missing_secret"
    | "circuit_open"
    | "transport_error"
    | "not_found"
    | "provider_error"
    | "malformed_response"
    | null;
};

const LONG_ANALYSES = [
  {
    id: "ana_appqa_long_001",
    compound_input:
      "Ultra-long stereoselective fermentation-route freedom-to-operate screen for succinic acid derivative",
    compound_name:
      "Ultra-long stereoselective fermentation-route freedom-to-operate screen",
    compound_smiles:
      "C[C@@H](O)C(=O)OCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: "high",
    blocking_patents_count: 3,
    total_patents_found: 2417,
    executive_summary:
      "Independent fermentation-route claims require counsel review.",
    estimated_cost_usd: 4.82,
    pipeline_duration_seconds: 842,
    flagged_for_review: true,
    review_status: {
      status: "under_review",
      is_persisted: true,
      note: "Counsel review queued",
      reviewer_name: "Demo Counsel",
      reviewer_email: "counsel@example.test",
      reviewed_at: null,
      updated_at: "2026-04-24T10:14:00Z",
    },
    share_active: true,
    share_view_count: 2,
    share_last_viewed_at: "2026-04-24T10:14:00Z",
    created_at: "2026-04-24T10:00:00Z",
    updated_at: "2026-04-24T10:14:00Z",
  },
  {
    id: "ana_appqa_running_002",
    compound_input: "ibuprofen",
    compound_name: "Ibuprofen",
    compound_smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    status: "running",
    current_step: 4,
    progress_pct: 52,
    overall_risk: null,
    blocking_patents_count: 0,
    total_patents_found: 183,
    executive_summary: "Triage in progress.",
    estimated_cost_usd: 1.24,
    pipeline_duration_seconds: null,
    flagged_for_review: false,
    review_status: null,
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: "2026-04-24T09:30:00Z",
    updated_at: "2026-04-24T09:38:00Z",
  },
] as const;

const COMPOUND_FIXTURES = [
  {
    id: "cmp_appqa_succinic",
    canonical_smiles: "OC(=O)CCC(O)=O",
    inchi_key: "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
    name: "Succinic acid",
    molecular_formula: "C4H6O4",
    molecular_weight: 118.09,
    functional_groups: ["carboxylic acid", "dicarboxylic acid"],
    pubchem_cid: 1110,
    first_analyzed_at: "2026-04-24T10:00:00Z",
    analysis_count: 3,
  },
  {
    id: "cmp_appqa_ibuprofen",
    canonical_smiles: "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    inchi_key: "HEFNNWSXXWATRW-UHFFFAOYSA-N",
    name: "Ibuprofen",
    molecular_formula: "C13H18O2",
    molecular_weight: 206.28,
    functional_groups: ["carboxylic acid", "aryl"],
    pubchem_cid: 3672,
    first_analyzed_at: "2026-04-23T09:00:00Z",
    analysis_count: 1,
  },
] as const;

const PATENT_FIXTURES = [
  {
    id: "pat_appqa_001",
    patent_number: "US10123456B2",
    title: "Fermentation route claims for substituted succinate derivatives",
    assignee: "Northstar Therapeutics",
    risk_level: "high",
    cpc_codes: ["C07C51/00", "C12P7/46"],
    expiry_date: "2031-08-14",
    analysis_id: LONG_ANALYSES[0].id,
    compound_name: "Succinic acid",
  },
  {
    id: "pat_appqa_002",
    patent_number: "EP3456789B1",
    title: "Crystalline anti-inflammatory composition",
    assignee: "Example Pharma AG",
    risk_level: "medium",
    cpc_codes: ["A61K31/192"],
    expiry_date: "2029-02-20",
    analysis_id: LONG_ANALYSES[1].id,
    compound_name: "Ibuprofen",
  },
] as const;

const MONITOR_FIXTURES = [
  {
    id: "mon_appqa_kras",
    compound_smiles: "CC(C)(C)OC(=O)N1CCN(CC1)c1ncnc2[nH]ccc12",
    compound_name: "KRAS G12C watch",
    source_analysis_id: LONG_ANALYSES[0].id,
    source_report_id: "report_appqa_001",
    source_trust_mode: "agentic",
    schedule: "weekly",
    is_active: true,
    jurisdiction_bundle: "us-eu",
    target_jurisdictions: ["US", "EP"],
    strategy_version: "2026.06",
    monitoring_strategy: { mode: "diff_only" },
    watch_targets: [],
    last_run_at: "2026-06-24T09:00:00Z",
    last_full_refresh_at: "2026-06-01T09:00:00Z",
    last_run_mode: "diff_only",
    last_run_status: "ready",
    last_run_summary: "No new blocking claims surfaced in the latest watch.",
    last_patent_count: 184,
    created_at: "2026-06-01T09:00:00Z",
  },
] as const;

const MONITOR_ALERT_FIXTURES = [
  {
    id: "alert_appqa_001",
    monitor_id: MONITOR_FIXTURES[0].id,
    new_patent_ids: ["US20260123456A1", "EP4123456A1"],
    new_patent_count: 2,
    run_at: "2026-06-24T09:00:00Z",
    dismissed: false,
    created_at: "2026-06-24T09:00:01Z",
    summary:
      "2 new continuation events need review before the next counsel packet.",
    alert_type: "new_publication",
    severity: "medium",
    strategy_mode: "diff_only",
    new_event_ids: ["evt_appqa_001", "evt_appqa_002"],
    jurisdiction_deltas: { US: 1, EP: 1 },
  },
] as const;

const BATCH_FIXTURES = [
  {
    id: "batch_appqa_series_a",
    name: "Series A diligence batch",
    total_compounds: 12,
    completed_count: 8,
    failed_count: 1,
    status: "running",
    analysis_ids: [LONG_ANALYSES[0].id, LONG_ANALYSES[1].id],
    created_at: "2026-06-20T08:00:00Z",
    updated_at: "2026-06-24T10:30:00Z",
  },
] as const;

function watchConsole(page: Page) {
  const errors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    errors.push(error.message);
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    if (failure?.errorText === "net::ERR_ABORTED") {
      return;
    }
    errors.push(
      `Request failed: ${request.method()} ${request.url()}${
        failure?.errorText ? ` (${failure.errorText})` : ""
      }`,
    );
  });

  return errors;
}

async function mockAppApis(page: Page) {
  let analysesMode: "empty" | "long" = "long";
  let ssoStatus: AppSurfaceSsoStatus = {
    sso_enabled: true,
    provider: "Okta",
    domains: [
      "very-long-enterprise-identity-provider-domain-with-many-subdelegations.research-and-legal-operations.praviar.example",
    ],
    status: "active",
    clerk_dashboard_url: "https://dashboard.clerk.com/apps/demo",
    sso_status_available: true,
    sso_last_synced_at: new Date().toISOString(),
    sso_status_stale: false,
    sso_unavailable_reason: null,
  };
  const notificationPreferences = {
    email_on_analysis_complete: true,
    email_on_monitor_alert: true,
    email_digest_frequency: "weekly",
  };

  await page.addInitScript(() => {
    window.localStorage.setItem("praviar_tour_complete", "true");
  });

  await page.route("**/api/v1/analyses**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    const analysisDetailMatch = pathname.match(/\/api\/v1\/analyses\/([^/]+)$/);
    const reviewerDecisionMatch = pathname.match(
      /\/api\/v1\/analyses\/([^/]+)\/decisions$/,
    );
    const flagMatch = pathname.match(/\/api\/v1\/analyses\/([^/]+)\/flag$/);
    const isKnownAnalysisId = (analysisId: string) =>
      LONG_ANALYSES.some((item) => item.id === analysisId);

    if (method === "POST" && pathname.endsWith("/api/v1/analyses")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(LONG_ANALYSES[0]),
      });
      return;
    }

    if (method === "GET" && reviewerDecisionMatch) {
      if (!isKnownAnalysisId(reviewerDecisionMatch[1])) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            detail: `Unhandled reviewer decisions mock: ${pathname}`,
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
      return;
    }

    if (method === "POST" && reviewerDecisionMatch) {
      if (!isKnownAnalysisId(reviewerDecisionMatch[1])) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            detail: `Unhandled reviewer decision write mock: ${pathname}`,
          }),
        });
        return;
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          id: "decision_appqa_001",
          finding_type: "patent",
          finding_ref: "pat_appqa_001",
          decision: "accept",
          note: "",
          edited_text: "",
          reviewer_user_id: "user_appqa",
          reviewer_name: "Demo Counsel",
          reviewer_email: "counsel@example.test",
          created_at: "2026-06-24T10:00:00Z",
          updated_at: "2026-06-24T10:00:00Z",
        }),
      });
      return;
    }

    if (method === "POST" && flagMatch) {
      if (!isKnownAnalysisId(flagMatch[1])) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: `Unhandled flag mock: ${pathname}` }),
        });
        return;
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ flagged_for_review: true }),
      });
      return;
    }

    if (method === "GET" && analysisDetailMatch) {
      const analysis = LONG_ANALYSES.find(
        (item) => item.id === analysisDetailMatch[1],
      );
      if (!analysis) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            detail: `Unhandled analysis detail mock: ${pathname}`,
          }),
        });
        return;
      }

      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(analysis),
      });
      return;
    }

    if (method !== "GET" || !pathname.endsWith("/api/v1/analyses")) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `Unhandled analyses mock: ${pathname}`,
        }),
      });
      return;
    }

    const items = analysesMode === "empty" ? [] : LONG_ANALYSES;

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items,
        total: items.length,
        page: 1,
        per_page: 20,
        status_counts: {
          all: items.length,
          pending: 0,
          running: items.filter((item) => item.status === "running").length,
          completed: items.filter((item) => item.status === "completed").length,
          failed: 0,
          cancelled: 0,
        },
      }),
    });
  });

  await page.route("**/api/v1/comments/review-queue**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        counts: {
          open_total: 1,
          mine: 1,
          assigned: 1,
          unassigned: 0,
          overdue: 0,
          escalated: 1,
        },
        items: [
          {
            id: "rq_appqa_001",
            analysis_id: LONG_ANALYSES[0].id,
            compound_name: LONG_ANALYSES[0].compound_name,
            analysis_status: "completed",
            overall_risk: "high",
            body: "Attorney review requested for blocking fermentation-route claims.",
            assigned_to: "user_appqa",
            assigned_reviewer_name: "Demo Counsel",
            assigned_reviewer_email: "counsel@example.test",
            queue_age_hours: 18,
            reply_count: 2,
            is_mine: true,
            is_overdue: false,
            escalation_event_count: 1,
            escalated_at: "2026-04-24T10:15:00Z",
            last_assignment_at: "2026-04-24T10:10:00Z",
            last_escalation_at: "2026-04-24T10:15:00Z",
            created_at: "2026-04-24T10:00:00Z",
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/comments/reviewers**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "user_appqa",
          label: "Demo Counsel",
          email: "counsel@example.test",
          role: "admin",
        },
      ]),
    });
  });

  await page.route("**/api/v1/comments?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/v1/configs/presets", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ id: "preset_appqa_001" }),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/v1/configs/defaults", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        can_manage: true,
        config: {
          search_max_ranked_results: 200,
          search_jurisdictions: ["US", "EP", "WO", "JP", "KR", "CN"],
          max_analysis_patents: 20,
          max_doe_candidates: 15,
          citation_traversal_enabled: true,
          citation_max_depth: 2,
          analysis_thinking_budget_tokens: 12000,
          hitl_enabled: false,
          hitl_checkpoints: [
            "search_review",
            "triage_review",
            "analysis_review",
            "report_review",
          ],
          hitl_auto_skip_minutes: 10,
        },
      }),
    });
  });

  await page.route("**/api/v1/compounds**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: COMPOUND_FIXTURES,
        total: COMPOUND_FIXTURES.length,
        page: 1,
        per_page: 20,
      }),
    });
  });

  await page.route("**/api/v1/patents**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: PATENT_FIXTURES,
        total: PATENT_FIXTURES.length,
        page: 1,
        per_page: 20,
      }),
    });
  });

  await page.route("**/api/v1/batch**", async (route) => {
    const { pathname } = new URL(route.request().url());

    if (/\/api\/v1\/batch\/[^/]+$/.test(pathname)) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(BATCH_FIXTURES[0]),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: BATCH_FIXTURES,
        total: BATCH_FIXTURES.length,
      }),
    });
  });

  await page.route("**/api/v1/monitors**", async (route) => {
    const { pathname } = new URL(route.request().url());

    if (/\/api\/v1\/monitors\/[^/]+\/alerts$/.test(pathname)) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          items: MONITOR_ALERT_FIXTURES,
          total: MONITOR_ALERT_FIXTURES.length,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: MONITOR_FIXTURES,
        total: MONITOR_FIXTURES.length,
      }),
    });
  });

  await page.route("**/api/v1/api-keys**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "key_appqa_001",
            name: "Production case workspace API",
            key_prefix: "sg_live_appqa",
            scopes: ["analyses:read", "reports:read", "reports:export"],
            expires_at: "2026-09-24T09:30:00.000Z",
            last_used_at: "2026-06-24T09:30:00.000Z",
            revoked: false,
            created_at: "2026-06-01T10:00:00.000Z",
          },
        ],
        total: 1,
        capabilities: {
          admin_org_id: "org_appqa",
          is_platform_superadmin: true,
          can_manage_org_billing: true,
          can_list_cross_org_users: true,
          can_manage_cross_org_user_roles: false,
          can_inspect_task_queue: true,
        },
      }),
    });
  });

  await page.route("**/api/v1/admin/sso/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(ssoStatus),
    });
  });

  await page.route("**/api/v1/admin/sso/configure", async (route) => {
    const request = route.request();
    const payload = request.postDataJSON() as { enable?: boolean } | null;
    const enable = payload?.enable ?? true;
    ssoStatus = enable
      ? {
          sso_enabled: true,
          provider: "Demo IdP",
          domains: ["demo.praviar.local"],
          status: "pending",
          clerk_dashboard_url: "/settings?demo_sso=clerk",
          sso_status_available: true,
          sso_last_synced_at: new Date().toISOString(),
          sso_status_stale: false,
          sso_unavailable_reason: null,
        }
      : {
          sso_enabled: false,
          provider: null,
          domains: [],
          status: "inactive",
          clerk_dashboard_url: null,
          sso_status_available: true,
          sso_last_synced_at: new Date().toISOString(),
          sso_status_stale: false,
          sso_unavailable_reason: null,
        };

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        status: ssoStatus.status,
        message: enable
          ? "Demo SSO setup is ready to complete in Clerk."
          : "Demo SSO disable flow is ready to complete in Clerk.",
        next_steps: enable
          ? [
              "Open the Clerk dashboard.",
              "Connect your identity provider.",
              "Verify an enrolled domain before enforcing SSO.",
            ]
          : [
              "Open the Clerk dashboard.",
              "Disable the enterprise connection.",
              "Confirm users can still sign in through another method.",
            ],
        clerk_dashboard_url: ssoStatus.clerk_dashboard_url,
      }),
    });
  });

  await page.route("**/api/v1/admin/health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        services: [
          { name: "api", status: "healthy", detail: "Routes responding" },
          { name: "worker", status: "healthy", detail: "0 stuck jobs" },
          { name: "redis", status: "healthy", detail: "Latency 1ms" },
        ],
        table_counts: { analyses: 24, monitors: 3, comments: 9 },
      }),
    });
  });

  await page.route("**/api/v1/admin/organizations**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "org_appqa",
            name: "Praviar Demo Org",
            slug: "praviar-demo",
            plan: "starter",
            user_count: 4,
            analysis_count: 18,
            max_analyses_per_month: 24,
            free_analyses_remaining: 6,
            created_at: "2026-06-01T10:00:00Z",
          },
        ],
        total: 1,
        capabilities: {
          admin_org_id: "org_appqa",
          is_platform_superadmin: true,
          can_manage_org_billing: true,
          can_list_cross_org_users: true,
          can_manage_cross_org_user_roles: false,
          can_inspect_task_queue: true,
        },
      }),
    });
  });

  await page.route("**/api/v1/admin/users**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "user_appqa",
            email: "counsel@example.test",
            full_name: "Demo Counsel",
            role: "admin",
            org_id: "org_appqa",
            org_name: "Praviar Demo Org",
            last_active_at: "2026-06-24T09:30:00Z",
            created_at: "2026-06-01T10:00:00Z",
          },
        ],
        total: 1,
      }),
    });
  });

  await page.route("**/api/v1/admin/metrics", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        daily: [
          { date: "2026-06-20", count: 4, cost: 2.18, errors: 0 },
          { date: "2026-06-21", count: 6, cost: 3.42, errors: 1 },
        ],
        total_analyses: 10,
        total_cost: 5.6,
        avg_duration_seconds: 612,
        error_rate: 0.02,
      }),
    });
  });

  await page.route("**/api/v1/admin/audit-logs**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "audit_appqa_001",
            action: "analysis.created",
            user_id: "user_appqa",
            user_email: "counsel@example.test",
            analysis_id: LONG_ANALYSES[0].id,
            details: { compound_name: LONG_ANALYSES[0].compound_name },
            ip_address: "127.0.0.1",
            created_at: "2026-06-24T10:00:00Z",
          },
        ],
        total: 1,
      }),
    });
  });

  await page.route("**/api/v1/admin/tasks", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        backend: "celery",
        detail: "Queue inspected",
        inspectable: true,
        active: [],
        reserved: [],
        scheduled_count: 0,
      }),
    });
  });

  await page.route("**/api/v1/admin/analytics/costs**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        daily_costs: [
          {
            date: "2026-06-20",
            total_cost_usd: 2.18,
            analysis_count: 4,
            total_input_tokens: 240000,
            total_output_tokens: 36000,
          },
        ],
        step_costs: [
          {
            step_name: "claim_analysis",
            total_cost_usd: 2.18,
            analysis_count: 4,
            avg_cost_usd: 0.545,
          },
        ],
        model_costs: [
          {
            model_name: "claude-sonnet-4-6",
            total_cost_usd: 2.18,
            total_input_tokens: 240000,
            total_output_tokens: 36000,
            request_count: 12,
          },
        ],
        total_cost_usd: 2.18,
        total_input_tokens: 240000,
        total_output_tokens: 36000,
        period: "month",
        start_date: "2026-06-01",
        end_date: "2026-06-30",
      }),
    });
  });

  await page.route("**/api/v1/admin/analytics/usage**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        org_usage: [
          {
            org_id: "org_appqa",
            org_name: "Praviar Demo Org",
            analysis_count: 10,
            total_cost_usd: 2.18,
            avg_cost_usd: 0.218,
          },
        ],
        status_breakdown: [
          { status: "completed", count: 9 },
          { status: "running", count: 1 },
        ],
        top_compounds: [
          {
            compound_name: "Succinic acid",
            compound_smiles: "OC(=O)CCC(O)=O",
            analysis_count: 3,
          },
        ],
        total_analyses: 10,
        avg_cost_per_analysis: 0.218,
        avg_duration_seconds: 612,
        period: "month",
      }),
    });
  });

  await page.route("**/api/v1/admin/analytics/models**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        models: [
          {
            model_name: "claude-sonnet-4-6",
            total_input_tokens: 240000,
            total_output_tokens: 36000,
            total_tokens: 276000,
            estimated_cost_usd: 2.18,
            request_count: 12,
            cache_hit_rate: 34,
          },
        ],
        total_tokens: 276000,
        total_cost_usd: 2.18,
        overall_cache_hit_rate: 34,
        period: "month",
      }),
    });
  });

  await page.route("**/api/v1/admin/analytics/audit-log**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "audit_analytics_appqa_001",
            org_id: "org_appqa",
            action: "analysis.created",
            user_id: "user_appqa",
            user_email: "counsel@example.test",
            analysis_id: LONG_ANALYSES[0].id,
            details: { compound_name: LONG_ANALYSES[0].compound_name },
            ip_address: "127.0.0.1",
            created_at: "2026-06-24T10:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 50,
        has_next: false,
      }),
    });
  });

  await page.route("**/api/v1/billing/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        org_id: "org_appqa",
        plan: "starter",
        stripe_customer_id: "cus_appqa",
        stripe_subscription_id: "sub_appqa",
        subscription_status: "active",
        current_period_start: "2026-06-01T00:00:00.000Z",
        current_period_end: "2026-07-01T00:00:00.000Z",
        analyses_used: 2,
        analyses_limit: 12,
        included_analyses_limit: 10,
        purchased_credits_balance: 2,
        cancel_at_period_end: false,
      }),
    });
  });

  await page.route("**/api/v1/billing/usage", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        org_id: "org_appqa",
        plan: "starter",
        analyses_used: 2,
        analyses_limit: 12,
        included_analyses_limit: 10,
        purchased_credits_balance: 2,
        usage_pct: 16.7,
        cost_this_month_cents: 4900,
        overage_analyses: 0,
        period_start: "2026-06-01T00:00:00.000Z",
        period_end: "2026-07-01T00:00:00.000Z",
      }),
    });
  });

  await page.route("**/api/v1/billing/invoices", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        invoices: [
          {
            id: "in_appqa_001",
            number: "PRV-2026-001",
            status: "paid",
            amount_due_cents: 4900,
            amount_paid_cents: 4900,
            currency: "usd",
            created_at: "2026-06-01T00:00:00.000Z",
            hosted_invoice_url: null,
            pdf_url: null,
          },
        ],
        has_more: false,
      }),
    });
  });

  await page.route("**/api/v1/notifications**", async (route) => {
    const method = route.request().method();
    const { pathname } = new URL(route.request().url());

    let body: unknown;
    if (method === "GET" && pathname.endsWith("/unread-count")) {
      body = { unread_count: 0 };
    } else if (pathname.endsWith("/preferences")) {
      body = notificationPreferences;
    } else if (
      method === "POST" &&
      (pathname.endsWith("/mark-read") || pathname.endsWith("/dismiss-all"))
    ) {
      body = { marked: 0 };
    } else if (method === "GET" && pathname.endsWith("/api/v1/notifications")) {
      body = { items: [], unread_count: 0, total: 0 };
    } else {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `Unhandled notifications mock: ${pathname}`,
        }),
      });
      return;
    }

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  return {
    setAnalysesMode(mode: "empty" | "long") {
      analysesMode = mode;
    },
    setSsoStatus(status: "active" | "pending" | "inactive") {
      ssoStatus =
        status === "active"
          ? {
              sso_enabled: true,
              provider: "Okta",
              domains: [
                "very-long-enterprise-identity-provider-domain-with-many-subdelegations.research-and-legal-operations.praviar.example",
              ],
              status,
              clerk_dashboard_url: "https://dashboard.clerk.com/apps/demo",
              sso_status_available: true,
              sso_last_synced_at: new Date().toISOString(),
              sso_status_stale: false,
              sso_unavailable_reason: null,
            }
          : status === "pending"
            ? {
                sso_enabled: true,
                provider: "Demo IdP",
                domains: ["demo.praviar.local"],
                status,
                clerk_dashboard_url: "/settings?demo_sso=clerk",
                sso_status_available: true,
                sso_last_synced_at: new Date().toISOString(),
                sso_status_stale: false,
                sso_unavailable_reason: null,
              }
            : {
                sso_enabled: false,
                provider: null,
                domains: [],
                status,
                clerk_dashboard_url: null,
                sso_status_available: true,
                sso_last_synced_at: new Date().toISOString(),
                sso_status_stale: false,
                sso_unavailable_reason: null,
              };
    },
  };
}

async function expectNoHorizontalOverflow(page: Page, label: string) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    const scrollWidth = Math.max(root.scrollWidth, document.body.scrollWidth);
    return scrollWidth - root.clientWidth;
  });

  expect(overflow, `${label} horizontal overflow`).toBeLessThanOrEqual(1);
}

async function expectBuyerTargetAtLeast44(locator: Locator, label: string) {
  await expect(locator, `${label} visible`).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} bounding box`).not.toBeNull();
  expect(box?.width ?? 0, `${label} width`).toBeGreaterThanOrEqual(44);
  expect(box?.height ?? 0, `${label} height`).toBeGreaterThanOrEqual(44);
}

async function expectVisibleInteractiveTargetsMeetMinimumSize(
  page: Page,
  label: string,
) {
  const undersizedTargets = await page.locator("main").evaluate((main) => {
    const selector = [
      "a[href]",
      "button",
      "input:not([type='hidden'])",
      "select",
      "textarea",
      "[role='button']",
      "[role='link']",
      "[role='checkbox']",
      "[role='radio']",
      "[role='switch']",
      "[role='tab']",
      "[role='menuitem']",
    ].join(",");

    return Array.from(main.querySelectorAll<HTMLElement>(selector))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        const labelText =
          element.getAttribute("aria-label") ??
          element.textContent?.trim().replace(/\s+/g, " ") ??
          element.tagName.toLowerCase();

        return {
          disabled:
            element.hasAttribute("disabled") ||
            element.getAttribute("aria-disabled") === "true",
          display: style.display,
          height: rect.height,
          label: labelText.slice(0, 80),
          visibility: style.visibility,
          width: rect.width,
        };
      })
      .filter(
        (target) =>
          !target.disabled &&
          target.display !== "none" &&
          target.visibility !== "hidden" &&
          target.width > 0 &&
          target.height > 0 &&
          (target.width < 24 || target.height < 24),
      );
  });

  expect(undersizedTargets, `${label} undersized interactive targets`).toEqual(
    [],
  );
}

async function expectReducedMotionSuppressesDecorativeAnimation(
  page: Page,
  label: string,
) {
  const motionState = await page.locator("main").evaluate((main) => {
    const animatedElements = Array.from(
      main.querySelectorAll<HTMLElement>(
        "[class*='animate-'], [class*='skeleton-shimmer']",
      ),
    )
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return {
          animationDuration: style.animationDuration,
          animationName: style.animationName,
          display: style.display,
          height: rect.height,
          label:
            element.getAttribute("aria-label") ??
            element.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) ??
            element.tagName.toLowerCase(),
          visibility: style.visibility,
          width: rect.width,
        };
      })
      .filter(
        (element) =>
          element.display !== "none" &&
          element.visibility !== "hidden" &&
          element.width > 0 &&
          element.height > 0 &&
          element.animationName !== "none" &&
          !/^(0s|0ms|0\.01ms)(,\s*(0s|0ms|0\.01ms))*$/.test(
            element.animationDuration,
          ),
      );

    return {
      animatedElements,
      scrollBehavior: window.getComputedStyle(document.documentElement)
        .scrollBehavior,
    };
  });

  expect(
    motionState.animatedElements,
    `${label} active reduced-motion animations`,
  ).toEqual([]);
  expect(motionState.scrollBehavior, `${label} reduced-motion scroll`).toBe(
    "auto",
  );
}

async function expectPremiumAppBranding(page: Page, label: string) {
  await expect
    .poll(
      async () =>
        page
          .locator("main [data-praviar-mark='praviar-evidence-mark']")
          .evaluateAll(
            (marks) =>
              marks.filter((mark) => {
                const rect = mark.getBoundingClientRect();
                const style = window.getComputedStyle(mark);
                return (
                  rect.width > 0 &&
                  rect.height > 0 &&
                  style.visibility !== "hidden" &&
                  style.display !== "none"
                );
              }).length,
          ),
      { message: `${label} visible page-level Praviar mark` },
    )
    .toBeGreaterThan(0);

  const appBackground = await page.evaluate(() => {
    const appField = document.querySelector(".praviar-app-field");
    return appField ? window.getComputedStyle(appField).backgroundImage : "";
  });

  expect(appBackground, `${label} app evidence field`).toContain(
    "praviar-app-evidence-field.svg",
  );
}

async function expectPremiumAuthBranding(page: Page, label: string) {
  const visibleMainMarkCount = await page
    .locator("main [data-praviar-mark='praviar-evidence-mark']")
    .evaluateAll(
      (marks) =>
        marks.filter((mark) => {
          const rect = mark.getBoundingClientRect();
          const style = window.getComputedStyle(mark);
          return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none"
          );
        }).length,
    );
  expect(
    visibleMainMarkCount,
    `${label} visible auth-surface Praviar mark`,
  ).toBeGreaterThan(0);

  const authBackground = await page.evaluate(() => {
    const authField = document.querySelector(".praviar-auth-field");
    return authField ? window.getComputedStyle(authField).backgroundImage : "";
  });

  expect(authBackground, `${label} auth evidence field`).toContain(
    "praviar-auth-evidence-field.svg",
  );
}

async function expectAuthControlSurface(page: Page, label: string) {
  const fallbackLedger = page.getByRole("region", {
    name: "Authentication trust ledger",
  });
  const fallbackRetry = page.getByRole("button", { name: "Try again" });
  const configuredClerkSurface = page
    .locator(
      ".praviar-dialog-panel, .cl-card, .cl-rootBox, [data-clerk-element]",
    )
    .first();

  await expect
    .poll(
      async () => {
        const fallbackVisible = await fallbackLedger
          .isVisible()
          .catch(() => false);
        const fallbackRetryVisible = await fallbackRetry
          .isVisible()
          .catch(() => false);
        const clerkVisible = await configuredClerkSurface
          .isVisible()
          .catch(() => false);
        return fallbackVisible || fallbackRetryVisible || clerkVisible;
      },
      { message: `${label} configured or sealed auth control surface` },
    )
    .toBe(true);

  if (await fallbackLedger.isVisible().catch(() => false)) {
    await expect(
      page.getByText(
        "Evidence remains sealed until the workspace identity provider is configured.",
      ),
    ).toBeVisible();
  } else if (await fallbackRetry.isVisible().catch(() => false)) {
    await expect(
      page.getByText("Compound evidence remains sealed."),
    ).toBeVisible();
  }
}

test.describe("app surface visual QA", () => {
  test.describe.configure({ mode: "serial", timeout: 120_000 });

  test("server-rendered theme satisfies the per-request CSP without hydration noise", async ({
    page,
  }) => {
    const consoleErrors = watchConsole(page);
    const response = await page.goto("/");
    expect(response).not.toBeNull();

    const nonce = response?.headers()["x-nonce"];
    expect(nonce).toMatch(/^[A-Za-z0-9_-]+$/u);
    expect(response?.headers()["content-security-policy"]).toContain(
      `'nonce-${nonce}'`,
    );

    await expect(page.locator("#praviar-theme-bootstrap")).toHaveCount(0);
    await expect(page.locator("html")).toHaveClass(/\blight\b/u);
    expect(consoleErrors).toEqual([]);
  });

  for (const viewport of VIEWPORTS) {
    test(`auth routes keep one landmark and appropriate proof at ${viewport.name}`, async ({
      page,
    }) => {
      const consoleErrors = watchConsole(page);
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });

      for (const route of AUTH_ROUTES) {
        await page.goto(route.path);
        const usesDemoSignInState =
          DEMO_FIXTURES_ENABLED && route.path === "/sign-in";
        const usesCompactDemoProof =
          usesDemoSignInState && viewport.width < 1024;
        if (usesDemoSignInState) {
          await expect(page.getByTestId("demo-sign-in-state")).toBeVisible();
        }
        if (usesCompactDemoProof) {
          const demoState = page.getByTestId("demo-sign-in-state");
          await expect(demoState).toBeVisible();
          await expect(
            demoState
              .locator("[data-praviar-mark='praviar-evidence-mark']")
              .first(),
          ).toBeVisible();
          await expect(
            demoState.getByRole("heading", { name: "Demo data only" }),
          ).toBeVisible();
          await expect(
            demoState.getByRole("link", { name: "Enter demo workspace" }),
          ).toBeVisible();
          await expect(page.getByTestId("auth-mobile-proof")).toHaveCount(0);
        } else {
          const proofRegion =
            viewport.width >= 1024
              ? page.getByTestId("auth-desktop-proof")
              : page.getByTestId("auth-mobile-proof");
          await expect(proofRegion).toHaveCount(1);
          await expect(proofRegion).toBeVisible();
          await expect(
            proofRegion.locator("[data-praviar-lockup='canonical']").first(),
          ).toBeVisible();
          await expect(
            proofRegion
              .locator("[data-praviar-mark='praviar-evidence-mark']")
              .first(),
          ).toBeVisible();
          await expect(proofRegion.getByText("Praviar access")).toHaveCount(0);
          await expect(
            proofRegion.getByText("Protected evidence workspace"),
          ).toBeVisible();
          await expect(
            proofRegion.getByText("Succinic acid review packet"),
          ).toHaveCount(0);
          await expect(proofRegion.getByText(/^HIGH$/)).toHaveCount(0);
        }
        if (!usesDemoSignInState) {
          await expectAuthControlSurface(
            page,
            `${route.path} at ${viewport.name}`,
          );
        }
        await expect(page.locator("main")).toHaveCount(1);
        await expect(page.locator("main main")).toHaveCount(0);
        await expectPremiumAuthBranding(
          page,
          `${route.path} at ${viewport.name}`,
        );
        await expectNoHorizontalOverflow(
          page,
          `${route.path} at ${viewport.name}`,
        );
        await expectVisibleInteractiveTargetsMeetMinimumSize(
          page,
          `${route.path} at ${viewport.name}`,
        );
      }

      expect(consoleErrors).toEqual([]);
    });
  }

  test("buyer-critical monitor, batch, and report-search targets are 44px at mobile width", async ({
    page,
  }) => {
    await mockAppApis(page);
    await page.setViewportSize({ width: 375, height: 812 });

    await page.goto("/monitors");
    await page.getByRole("button", { name: "New Monitor" }).click();
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: "Close create monitor form" }),
      "monitor close",
    );
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: "Cancel" }),
      "monitor cancel",
    );
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: "Create Monitor", exact: true }),
      "monitor create",
    );
    await page.getByRole("button", { name: "Cancel" }).click();

    await page.goto("/batch");
    await page.getByRole("button", { name: "New Batch" }).click();
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: "Cancel", exact: true }),
      "batch cancel",
    );
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: /^Start Batch/u }),
      "batch start",
    );

    await page.goto("/analyses/ana_demo_001/report");
    const reportSearch = page.getByLabel("Search report");
    await expectBuyerTargetAtLeast44(reportSearch, "report search input");
    await reportSearch.fill("patent");
    await expectBuyerTargetAtLeast44(
      page.getByRole("button", { name: "Clear search" }),
      "report search clear",
    );
  });

  for (const viewport of VIEWPORTS) {
    test(`core app routes stay polished without overflow at ${viewport.name}`, async ({
      page,
    }) => {
      const api = await mockAppApis(page);
      const consoleErrors = watchConsole(page);
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });

      for (const route of APP_ROUTES) {
        api.setAnalysesMode(route.path === "/dashboard" ? "empty" : "long");
        await page.goto(route.path);
        await expect(
          page.locator("main").getByRole("heading", {
            name: route.heading,
            exact: true,
          }),
        ).toBeVisible();
        await expect(
          page.locator("main").getByText(route.proofText).first(),
        ).toBeVisible();
        await expectPremiumAppBranding(
          page,
          `${route.path} at ${viewport.name}`,
        );
        await expectNoHorizontalOverflow(
          page,
          `${route.path} at ${viewport.name}`,
        );
      }

      expect(consoleErrors).toEqual([]);
    });
  }

  test("settings SSO details keep demo setup flow mobile-safe", async ({
    page,
  }) => {
    const api = await mockAppApis(page);
    api.setSsoStatus("inactive");
    const consoleErrors = watchConsole(page);

    for (const viewport of [
      { name: "320px", width: 320, height: 812 },
      { name: "375px", width: 375, height: 812 },
      { name: "390px", width: 390, height: 844 },
    ] as const) {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.goto("/settings");
      await page
        .getByLabel("Identity & Sign-On")
        .getByRole("button", { name: /^Manage$/ })
        .click();
      await expect(
        page.getByRole("region", { name: "SSO configuration details" }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: /^(Start|Continue) SSO setup$/ })
        .click();

      await expect(
        page.getByText("Demo SSO setup is ready to complete in Clerk."),
      ).toBeVisible();
      await expect(page.getByText("demo.praviar.local")).toBeVisible();
      await expectNoHorizontalOverflow(
        page,
        `settings SSO setup at ${viewport.name}`,
      );
    }

    expect(consoleErrors).toEqual([]);
  });

  test.describe("reduced motion contract", () => {
    test.use({
      allowedConsoleWarningPrefixes: [
        "You have Reduced Motion enabled on your device.",
      ],
    });

    test("dashboard respects reduced motion while preserving brand proof", async ({
      page,
    }) => {
      const api = await mockAppApis(page);
      api.setAnalysesMode("empty");
      const consoleErrors = watchConsole(page);
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/dashboard");

      await expect(
        page.locator("main").getByRole("heading", {
          name: "Dashboard",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.locator("main").getByText("Patent intelligence workspace").first(),
      ).toBeVisible();
      await expectPremiumAppBranding(page, "reduced-motion dashboard");
      await expectNoHorizontalOverflow(page, "reduced-motion dashboard");
      await expectVisibleInteractiveTargetsMeetMinimumSize(
        page,
        "reduced-motion dashboard",
      );
      await expectReducedMotionSuppressesDecorativeAnimation(
        page,
        "reduced-motion dashboard",
      );

      expect(consoleErrors).toEqual([]);
    });
  });

  test("new analysis wizard keeps configure and review steps mobile-safe", async ({
    page,
  }) => {
    await mockAppApis(page);
    const consoleErrors = watchConsole(page);
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/analyses/new");

    await page
      .getByPlaceholder("Name, SMILES, InChI, CAS")
      .fill("succinic acid");
    await page.getByRole("button", { name: "Confirm for resolution" }).click();
    await expect(
      page.getByRole("button", { name: "Submitted identity confirmed" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Next: Configure" }).click();

    await expect(page.getByText("Analysis Configuration")).toBeVisible();
    await page.getByRole("button", { name: "Expert Settings" }).click();
    await page.getByRole("button", { name: "Search Parameters" }).click();
    await page.getByText("Patent Sources").scrollIntoViewIfNeeded();
    await expect(page.getByText("Patent Sources")).toBeVisible();
    await expectNoHorizontalOverflow(page, "wizard configure step");

    await page.getByRole("button", { name: "Save as Preset" }).click();
    await expect(
      page.getByPlaceholder("e.g., Counsel review baseline"),
    ).toBeVisible();
    await expect(page.getByPlaceholder("Brief description")).toBeVisible();
    await expectNoHorizontalOverflow(page, "wizard save-preset panel");

    await page.getByRole("button", { name: "Next: Review" }).click();
    await expect(page.getByText("Confirm & Launch")).toBeVisible();
    await expect(
      page
        .getByTestId("review-launch-source-card")
        .getByText("PubChem, BigQuery, SureChEMBL, PatCID"),
    ).toBeVisible();
    await expect(page.getByText("Target lanes")).toBeVisible();
    await expect(page.getByText("Review Gates", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start Analysis" }),
    ).toBeVisible();
    await expectNoHorizontalOverflow(page, "wizard review step");

    expect(consoleErrors).toEqual([]);
  });

  test("mobile sidebar opens, navigates, and closes without overflow", async ({
    page,
  }) => {
    const api = await mockAppApis(page);
    api.setAnalysesMode("empty");
    const consoleErrors = watchConsole(page);
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/dashboard");

    const sidebar = page.locator("#dashboard-sidebar");
    let sidebarBox = await sidebar.boundingBox();
    expect(sidebarBox?.x ?? 0).toBeLessThanOrEqual(-250);

    await page.getByLabel("Open navigation menu").click();
    await expect
      .poll(async () => (await sidebar.boundingBox())?.x ?? -999)
      .toBeGreaterThanOrEqual(-1);
    sidebarBox = await sidebar.boundingBox();
    expect(sidebarBox?.width ?? 0).toBeLessThanOrEqual(256);
    await expectNoHorizontalOverflow(page, "open mobile sidebar");

    api.setAnalysesMode("long");
    await sidebar.getByRole("link", { name: "Analyses" }).click();
    await expect(page).toHaveURL(/\/analyses/);
    await expect(
      page.getByRole("heading", { name: "Analysis Library" }),
    ).toBeVisible();
    await expect
      .poll(async () => (await sidebar.boundingBox())?.x ?? 0)
      .toBeLessThanOrEqual(-250);
    await expectNoHorizontalOverflow(page, "closed mobile sidebar after nav");

    expect(consoleErrors).toEqual([]);
  });

  test("first-run welcome packet remains mobile-safe and proof-led", async ({
    page,
  }) => {
    await mockAppApis(page);
    const consoleErrors = watchConsole(page);
    await page.setViewportSize({ width: 320, height: 812 });
    const demoOnboardingKeys = onboardingStorageKeys(DEMO_ONBOARDING_IDENTITY);
    expect(demoOnboardingKeys).not.toBeNull();
    await page.addInitScript((welcomeKey) => {
      window.localStorage.removeItem("praviar_welcomed");
      window.localStorage.removeItem(welcomeKey);
    }, demoOnboardingKeys?.welcome ?? "missing-demo-welcome-key");

    await page.goto("/dashboard");
    await expect(page.getByText("Step 1 of 3")).toBeVisible();
    await expect(page.getByTestId("welcome-packet-preview")).toBeVisible();
    await expect(page.getByText("Not a legal opinion")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Next", exact: true }),
    ).toBeVisible();
    await expectNoHorizontalOverflow(page, "first-run welcome modal");

    expect(consoleErrors).toEqual([]);
  });

  test("dashboard entry actions are links without nested interactive controls", async ({
    page,
  }) => {
    const api = await mockAppApis(page);
    api.setAnalysesMode("empty");
    const consoleErrors = watchConsole(page);
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto("/dashboard");

    const startLink = page.getByRole("link", { name: "New Analysis" }).first();

    await expect(startLink).toHaveAttribute("href", "/analyses/new");

    const nestedInteractiveCount = await page.evaluate(
      () =>
        document.querySelectorAll(
          "a[href] button, button a[href], a[href] [role='button'], [role='button'] a[href], button button",
        ).length,
    );

    expect(nestedInteractiveCount).toBe(0);
    await expectNoHorizontalOverflow(page, "dashboard entry actions");
    expect(consoleErrors).toEqual([]);
  });
});
