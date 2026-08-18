/**
 * Component-test state only. All legal records, people, organizations,
 * publication identifiers, citations, and outcomes are synthetic. This file is
 * not the canonical showcase and is not release evidence.
 */

import type { Page, Route } from "@playwright/test";
import { TEST_REPORT } from "../../../src/lib/demo-report";
import { getDemoAnalysis } from "../../../src/lib/demo-data";
import {
  VISUAL_MATRIX_API_KEY_ID,
  VISUAL_MATRIX_API_REPORT_ID,
  VISUAL_MATRIX_CLAIM_ASSERTION_ID,
  VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID,
  VISUAL_MATRIX_COMMENT_ID,
  VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID,
  VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID,
  VISUAL_MATRIX_MONITOR_ALERT_ID,
  VISUAL_MATRIX_MONITOR_ID,
  VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE,
} from "./visual-matrix-routes";

export const SENDER_RECIPIENT = "visual.reviewer@example.invalid";
export const SENDER_SHARE_TOKEN = "sg_visual_sender_grant_7Kp2mQ9xV4cN8rT6wH3z";

const DEMO_REPORT_ID = "ana_demo_001";
const GRANT_ID = "grant_visual_existing_001";
const DEMO_REPORT_ANALYSIS = getDemoAnalysis(DEMO_REPORT_ID);

if (!DEMO_REPORT_ANALYSIS) {
  throw new Error("Visual matrix report analysis fixture is unavailable");
}

export const API_REPORT = {
  ...TEST_REPORT,
  report_id: "rpt_visual_api_001",
  invalidity_assessments: TEST_REPORT.invalidity_assessments.map(
    (assessment) => ({
      ...assessment,
      overall_invalidity_strength:
        assessment.overall_invalidity_strength === "moderate-strong"
          ? "strong"
          : assessment.overall_invalidity_strength,
    }),
  ),
} as const;

const CLAIM_SOURCE_TEXT_SHA256 =
  "c4c9bbca6c9f89ab690f696a59f9bbfbc9eea12ec724cf1be898a28d2469dc87";

export const CLAIM_DECISION_MATRIX_REPORT = {
  ...API_REPORT,
  claim_source_span_map: {
    generated_from: "visual_matrix_claim_decision_fixture",
    entries: [
      {
        assertion_id: `${VISUAL_MATRIX_CLAIM_ASSERTION_ID}-source`,
        patent_id: "US0000000001A1",
        claim_number: 1,
        element_number: 1,
        report_section: "verified_claim_text",
        assertion_text:
          "Synthetic component-test wording for claim 1 element 1 is linked to a synthetic fixture receipt.",
        source_span_ids: [VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID],
        support_status: "supported",
        customer_visible: true,
        review_required: false,
      },
      {
        assertion_id: VISUAL_MATRIX_CLAIM_ASSERTION_ID,
        patent_id: "US0000000001A1",
        claim_number: 1,
        element_number: 1,
        report_section: "claim_element_analysis",
        assertion_text:
          "Claim 1 element 1 maps to the evaluated recombinant prokaryotic production route and requires counsel review.",
        source_span_ids: [],
        support_status: "needs_review",
        customer_visible: true,
        review_required: true,
      },
    ],
    spans: {
      [VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID]: {
        span_id: VISUAL_MATRIX_CLAIM_SOURCE_SPAN_ID,
        source_type: "verified_claim_text",
        patent_id: "US0000000001A1",
        claim_number: 1,
        element_number: 1,
        citation: "US0000000001A1 claim 1 · synthetic fixture text",
        excerpt:
          "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism.",
        source_document_id: "US0000000001A1",
        source_name: "Synthetic authority-like component-test record",
        source_text_sha256: CLAIM_SOURCE_TEXT_SHA256,
        source_retrieved_at: "2026-07-15T09:30:00.000Z",
        source_artifact_locator: `https://example.invalid/component-test/patent/US0000000001A1#sha256=${CLAIM_SOURCE_TEXT_SHA256}`,
        collector_identity: "fixture.synthetic_claims",
        collector_version: "fixture-v1",
        provenance_cassette_sha256:
          "0e0f248bde1b00cba10db3e41599418bc05cc3c012c628d04a57fc6529b9c94d",
      },
    },
    unsupported_customer_visible_claim_count: 0,
    needs_review_count: 1,
  },
} as const;

export const API_REPORT_ANALYSIS = {
  ...DEMO_REPORT_ANALYSIS,
  id: VISUAL_MATRIX_API_REPORT_ID,
  input_type: "name",
  submitted_identity_confirmed: true,
  submitted_identity_value: DEMO_REPORT_ANALYSIS.compound_input.trim(),
  current_user_role: "attorney",
} as const;

export const LAUNCHED_ANALYSIS = {
  ...API_REPORT_ANALYSIS,
  id: VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID,
  compound_input: "succinic acid",
  compound_name: "Succinic acid",
  compound_smiles: "OC(=O)CCC(O)=O",
  status: "pending",
  current_step: 0,
  progress_pct: 0,
  overall_risk: null,
  blocking_patents_count: 0,
  total_patents_found: 0,
  executive_summary: "",
  pipeline_duration_seconds: null,
  flagged_for_review: false,
  review_status: {
    status: "pending",
    is_persisted: false,
  },
  created_at: "2026-07-16T08:45:00.000Z",
  updated_at: "2026-07-16T08:45:00.000Z",
} as const;

export const ANALYSIS_LIST = {
  items: [],
  total: 0,
  page: 1,
  per_page: 20,
  status_counts: {
    all: 0,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  },
} as const;

export const MONITOR_LIST = {
  items: [],
  total: 0,
} as const;

export const VISUAL_MONITOR = {
  id: VISUAL_MATRIX_MONITOR_ID,
  compound_smiles: "OC(=O)CCC(O)=O",
  compound_name: "Visual process watch",
  source_analysis_id: VISUAL_MATRIX_API_REPORT_ID,
  source_report_id: API_REPORT.report_id,
  source_trust_mode: "counsel",
  schedule: "weekly",
  is_active: true,
  jurisdiction_bundle: "custom",
  target_jurisdictions: ["US", "EP"],
  strategy_version: "visual-matrix-v1",
  monitoring_strategy: {
    mode: "report_grounded",
    evidence_scope: "retained_report",
  },
  watch_targets: [
    {
      patent_id: "US0000000001A1",
      risk_level: "high",
    },
  ],
  last_run_at: "2026-07-15T06:30:00.000Z",
  last_full_refresh_at: "2026-07-13T06:30:00.000Z",
  last_run_mode: "diff_only",
  last_run_status: "ready",
  last_run_summary:
    "One new continuation requires review against the retained report scope.",
  last_patent_count: 2417,
  created_at: "2026-06-15T08:00:00.000Z",
} as const;

export const MONITOR_LIST_WITH_ITEM = {
  items: [VISUAL_MONITOR],
  total: 1,
} as const;

export const VISUAL_MONITOR_ALERT = {
  id: VISUAL_MATRIX_MONITOR_ALERT_ID,
  monitor_id: VISUAL_MATRIX_MONITOR_ID,
  alert_type: "new_patent_delta",
  severity: "high",
  summary:
    "A new continuation in the retained succinic-acid process family requires counsel review.",
  strategy_mode: "report_grounded",
  new_patent_ids: ["US0000000020A1"],
  new_event_ids: ["continuation-filed"],
  jurisdiction_deltas: { US: 1 },
  new_patent_count: 1,
  run_at: "2026-07-15T06:30:00.000Z",
  dismissed: false,
  created_at: "2026-07-15T06:35:00.000Z",
} as const;

export const MONITOR_ALERT_LIST = {
  items: [VISUAL_MONITOR_ALERT],
  total: 1,
} as const;

const ACTIVE_GRANT = {
  id: GRANT_ID,
  recipient_email: "named.counsel@example.com",
  recipient_domain: "example.com",
  invitation_sent_at: "2026-07-12T10:00:00.000Z",
  expires_at: "2026-07-20T10:00:00.000Z",
  revoked_at: null,
  max_views: 25,
  view_count: 2,
  download_allowed: false,
  last_accessed_at: "2026-07-13T09:30:00.000Z",
  status: "active",
} as const;

const CREATED_GRANT = {
  ...ACTIVE_GRANT,
  id: "grant_visual_sender_002",
  recipient_email: SENDER_RECIPIENT,
  invitation_sent_at: "2026-07-13T10:00:00.000Z",
  last_accessed_at: null,
  share_token: SENDER_SHARE_TOKEN,
  status: "active",
  view_count: 0,
  invitation_status: "provider_accepted",
  replayed: false,
} as const;

const DEFAULT_ACTIVITY = [
  {
    id: "activity_visual_dispatch_001",
    event: "delivery_dispatch_started",
    occurred_at: "2026-07-12T09:59:58.000Z",
    view_number: null,
  },
  {
    id: "activity_visual_provider_001",
    event: "delivery_provider_accepted",
    occurred_at: "2026-07-12T10:00:00.000Z",
    view_number: null,
  },
  {
    id: "activity_visual_001",
    event: "invitation_sent",
    occurred_at: "2026-07-12T10:00:02.000Z",
    view_number: null,
  },
  {
    id: "activity_visual_002",
    event: "recipient_verified",
    occurred_at: "2026-07-13T09:25:00.000Z",
    view_number: null,
  },
  {
    id: "activity_visual_003",
    event: "report_viewed",
    occurred_at: "2026-07-13T09:30:00.000Z",
    view_number: 2,
  },
] as const;

export const BILLING_STATUS = {
  org_id: "11111111-1111-4111-8111-111111111111",
  can_manage_billing: true,
  plan: "starter",
  stripe_customer_id: "cus_visual",
  stripe_subscription_id: "sub_visual",
  subscription_status: "active",
  current_period_start: "2026-07-01T00:00:00.000Z",
  current_period_end: "2026-08-01T00:00:00.000Z",
  analyses_used: 2,
  analyses_limit: 12,
  included_analyses_limit: 10,
  purchased_credits_balance: 2,
  cancel_at_period_end: false,
} as const;

export const USAGE = {
  org_id: BILLING_STATUS.org_id,
  plan: "starter",
  analyses_used: 2,
  analyses_limit: 12,
  included_analyses_limit: 10,
  purchased_credits_balance: 2,
  usage_pct: 16.7,
  cost_this_month_cents: 49_000,
  currency: "usd",
  overage_analyses: 0,
  period_start: "2026-07-01T00:00:00.000Z",
  period_end: "2026-08-01T00:00:00.000Z",
} as const;

export const CREDIT_PACK_RECONCILIATION_APPLIED = {
  status: "applied",
  session_id: VISUAL_MATRIX_CREDIT_CHECKOUT_SESSION_ID,
  ledger_entry_id: "77777777-7777-4777-8777-777777777777",
  credit_pack_id: "portfolio_5",
  credits_applied: 5,
  current_purchased_credits_balance: 7,
  applied_at: "2026-07-16T08:40:00.000Z",
} as const;

export const ADMIN_CAPABILITIES = {
  admin_org_id: BILLING_STATUS.org_id,
  is_platform_superadmin: true,
  can_manage_org_billing: true,
  can_list_cross_org_users: true,
  can_manage_cross_org_user_roles: true,
  can_inspect_task_queue: true,
} as const;

export const VISUAL_USER = {
  id: "22222222-2222-4222-8222-222222222222",
  email: "visual.buyer@example.com",
  full_name: "Visual Buyer",
  role: "admin",
  org_id: BILLING_STATUS.org_id,
  org_name: "Praviar Visual Workspace",
  last_active_at: "2026-07-13T09:30:00.000Z",
  membership_active: true,
  membership_synchronized: true,
  created_at: "2026-06-01T10:00:00.000Z",
} as const;

export const ADMIN_OPERATION = {
  operation_id: "33333333-3333-4333-8333-333333333333",
  operation_type: "invite",
  state: "role_call_started",
  outcome_confirmed: false,
  reconciliation_required: true,
  provider_resource_id: null,
  target_user_id: null,
  target_email_normalized: "visual.buyer@example.com",
  requested_role: "attorney",
  updated_at: "2026-07-14T08:00:00.000Z",
} as const;

export const INVOICE_LIST = {
  invoices: [
    {
      id: "in_visual_001",
      number: "PRV-2026-001",
      status: "paid",
      amount_due_cents: 49_000,
      amount_paid_cents: 49_000,
      currency: "usd",
      created_at: "2026-07-01T00:00:00.000Z",
      hosted_invoice_url: null,
      pdf_url: null,
    },
  ],
  has_more: false,
} as const;

export const SSO_STATUS = {
  sso_enabled: false,
  provider: null,
  domains: [],
  status: "inactive",
  clerk_dashboard_url: null,
  sso_status_available: true,
  sso_last_synced_at: "2026-07-17T12:00:00.000Z",
  sso_status_stale: false,
  sso_unavailable_reason: null,
} as const;

export const SSO_STATUS_ACTIVE = {
  sso_enabled: true,
  provider: "Okta Workforce Identity",
  domains: ["praviar-visual.example.com", "counsel.example.com"],
  status: "active",
  clerk_dashboard_url:
    "https://dashboard.clerk.com/organizations/org_visual/sso-connections",
  sso_status_available: true,
  sso_last_synced_at: "2026-07-17T12:00:00.000Z",
  sso_status_stale: false,
  sso_unavailable_reason: null,
} as const;

export const API_KEY_LIST = { items: [], total: 0 } as const;

export const VISUAL_API_KEY = {
  id: VISUAL_MATRIX_API_KEY_ID,
  name: "Visual pipeline key",
  key_prefix: "prv_visual_pipeline",
  scopes: ["analyses:read", "reports:read", "reports:export"],
  expires_at: "2026-10-16T08:00:00.000Z",
  last_used_at: "2026-07-15T10:30:00.000Z",
  revoked: false,
  created_at: "2026-06-16T08:00:00.000Z",
} as const;

export const API_KEY_LIST_WITH_ITEM = {
  items: [VISUAL_API_KEY],
  total: 1,
} as const;

export const VISUAL_COMMENT = {
  id: VISUAL_MATRIX_COMMENT_ID,
  user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  body: "Confirm the independent-claim mapping before the report is used for launch clearance.",
  target_type: "analysis",
  target_id: VISUAL_MATRIX_API_REPORT_ID,
  parent_id: null,
  resolved: false,
  resolved_by: null,
  resolved_at: null,
  assigned_to: null,
  assigned_by: null,
  assigned_at: null,
  assigned_reviewer_name: null,
  assigned_reviewer_email: null,
  assignment_event_count: 0,
  last_assignment_at: null,
  queue_age_hours: 4,
  is_overdue: false,
  escalation_status: "none",
  escalated_by: null,
  escalated_at: null,
  escalated_by_name: null,
  escalated_by_email: null,
  escalation_event_count: 0,
  last_escalation_at: null,
  escalated_to_review: false,
  review_handoff_comment_id: null,
  created_at: "2026-07-16T06:00:00.000Z",
} as const;

export const COMMENT_LIST = [VISUAL_COMMENT] as const;

export const EXTERNAL_SHARING_POLICY = {
  mode: "approved_domains_only",
  approved_domains: ["example.com"],
  version: 1,
} as const;

export const REVIEWER_DECISION_LIST = {
  items: [],
  counts: { accept: 0, reject: 0, edit: 0 },
} as const;

export const SAVED_REVIEWER_DECISION = {
  id: "77777777-7777-4777-8777-777777777777",
  analysis_id: VISUAL_MATRIX_API_REPORT_ID,
  finding_type: "patent",
  finding_ref: "US0000000001A1",
  decision: "reject",
  note: "Counsel rejected this finding after source review.",
  edited_text: "",
  reviewer_user_id: "visual-reviewer-1",
  reviewer_name: "Visual Counsel",
  reviewer_email: "visual.reviewer@example.invalid",
  created_at: "2026-07-16T08:46:00.000Z",
  updated_at: "2026-07-16T08:46:00.000Z",
} as const;

export const EXPORT_REVIEWER_DECISION_LIST = {
  items: [
    SAVED_REVIEWER_DECISION,
    {
      ...SAVED_REVIEWER_DECISION,
      id: "77777777-7777-4777-8777-777777777778",
      decision: "accept",
      note: "Second counsel review confirmed the retained finding.",
      reviewer_user_id: "visual-reviewer-2",
      reviewer_name: "Second Visual Counsel",
      reviewer_email: "second.visual.reviewer@example.invalid",
    },
    {
      ...SAVED_REVIEWER_DECISION,
      id: "77777777-7777-4777-8777-777777777779",
      finding_ref: "US0000000002A1",
      decision: "accept",
      note: "Counsel confirmed the Fictional Atlas finding for export.",
      reviewer_user_id: "visual-reviewer-1",
    },
    {
      ...SAVED_REVIEWER_DECISION,
      id: "77777777-7777-4777-8777-777777777780",
      finding_ref: "US0000000002A1",
      decision: "reject",
      note: "Independent review recorded for the Fictional Atlas finding.",
      reviewer_user_id: "visual-reviewer-2",
      reviewer_name: "Second Visual Counsel",
      reviewer_email: "second.visual.reviewer@example.invalid",
    },
    {
      ...SAVED_REVIEWER_DECISION,
      id: "77777777-7777-4777-8777-777777777781",
      finding_ref: "US0000000003A1",
      decision: "accept",
      note: "Counsel confirmed the medium-risk Fictional Nova finding for export.",
    },
  ],
  counts: { accept: 3, reject: 2, edit: 0 },
} as const;

export const VISUAL_MATRIX_EXPORT_JOB_ID =
  "88888888-8888-4888-8888-888888888888";

export const COMPLETED_EXPORT_BODY = JSON.stringify({
  report_id: API_REPORT.report_id,
  analysis_id: VISUAL_MATRIX_API_REPORT_ID,
  verification: "fixture-backed export download",
});

export const COMPLETED_EXPORT_JOB = {
  job_id: VISUAL_MATRIX_EXPORT_JOB_ID,
  status: "completed",
  download_url: `/api/v1/exports/${VISUAL_MATRIX_EXPORT_JOB_ID}/download`,
  format: "json",
  file_size_bytes: new TextEncoder().encode(COMPLETED_EXPORT_BODY).byteLength,
  manifest_schema_version: "export-manifest-v1",
  manifest_hash:
    "a29a8f1f3f574bf4a135b45eeb8aa2211270f92c6f067b55cf1ad0cbdb191b55",
  manifest_snapshot: {
    artifact: {
      title: "Full Report · JSON Data",
      format: "json",
      sections: ["executive_summary", "patent_analysis", "audit_trail"],
    },
    readiness: { export_ready: true, review_status: "approved" },
  },
  artifact_sha256:
    "3adfd0e5d7e128eb0a9fc62c8f6dc44465da3ef6adfdfc81ff6af4184435c4c8",
  report_payload_sha256:
    "5b4ab351b5bd2ac97d10f35200f5f2bbbe6af739b0628c1d7080668f4dfc0f02",
  completed_at: "2026-07-16T08:48:00.000Z",
  error_message: null,
  retryable: false,
  retry_after_seconds: null,
} as const;

export const PENDING_EXPORT_JOB = {
  job_id: VISUAL_MATRIX_EXPORT_JOB_ID,
  status: "pending",
  download_url: null,
  format: "json",
  file_size_bytes: 0,
  manifest_schema_version: null,
  manifest_hash: null,
  manifest_snapshot: null,
  artifact_sha256: null,
  report_payload_sha256: null,
  completed_at: null,
  error_message: null,
  retryable: false,
  retry_after_seconds: null,
} as const;

export const NOTIFICATION_UNREAD_COUNT = { unread_count: 0 } as const;

export const NOTIFICATION_LIST = {
  items: [],
  unread_count: 0,
  total: 0,
} as const;

export const NOTIFICATION_PREFERENCES = {
  email_on_analysis_complete: true,
  email_on_monitor_alert: true,
  email_digest_frequency: "weekly",
} as const;

const REPORT_CHAT_SUCCESS_TEXT =
  "US0000000001A1 is the lead high-risk family because claim 1 maps directly to the evaluated succinic-acid process. Verify the cited claim language before relying on this screening result.";

export const REPORT_CHAT_SUCCESS_STREAM = [
  `data: ${JSON.stringify({
    type: "meta",
    conversation_id: "99999999-9999-4999-8999-999999999999",
    workspace_meta: {
      trust_mode: "counsel",
      mode_label: "Counsel workspace",
      capability_label: "Report-grounded answers",
      scope_label: "small_molecule · fto",
      source_coverage: "Retained report evidence",
      evidence_mode: "Report-grounded only",
      monitor_state: "Monitoring actions allowed",
      tool_access: ["evidence_search", "review_handoff", "monitor", "export"],
    },
  })}`,
  `data: ${JSON.stringify({
    type: "text",
    text: REPORT_CHAT_SUCCESS_TEXT,
  })}`,
  `data: ${JSON.stringify({
    type: "citation",
    citation: {
      cited_text:
        "Claim 1 covers the evaluated succinic-acid manufacturing process.",
      document_index: 0,
      document_title:
        "US0000000001A1 - Recombinant production of organic acids",
      patent_id: "US0000000001A1",
      claim_number: 1,
      element_number: 1,
      source_url: "https://example.invalid/patent/US0000000001A1",
    },
  })}`,
  `data: ${JSON.stringify({
    type: "done",
    citations: [
      {
        cited_text:
          "Claim 1 covers the evaluated succinic-acid manufacturing process.",
        document_index: 0,
        document_title:
          "US0000000001A1 - Recombinant production of organic acids",
        patent_id: "US0000000001A1",
        claim_number: 1,
        element_number: 1,
        source_url: "https://example.invalid/patent/US0000000001A1",
      },
    ],
  })}`,
  "",
].join("\n\n");

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function shareState(name: string) {
  const unknown = {
    ...ACTIVE_GRANT,
    invitation_sent_at: null,
    last_accessed_at: null,
    status: "delivery_outcome_unknown",
    view_count: 0,
  };
  if (name === "share-delivery-reconciliation-alert") {
    return {
      activity: [
        {
          id: "activity_visual_alert_001",
          event: "delivery_reconciliation_alert",
          occurred_at: "2026-07-14T08:20:00.000Z",
          view_number: null,
        },
      ],
      grants: [{ ...unknown, status: "delivery_reconciliation_alert" }],
    };
  }
  if (name === "share-delivery-cancelled-retention") {
    return {
      activity: [
        {
          id: "activity_visual_retention_001",
          event: "delivery_cancelled_retention_expired",
          occurred_at: "2026-07-14T08:10:00.000Z",
          view_number: null,
        },
      ],
      grants: [{ ...unknown, status: "delivery_cancelled_retention_expired" }],
    };
  }
  if (
    name === "share-delivery-outcome-unknown" ||
    name === "share-delivery-outcome-cancel-confirm" ||
    name === "share-delivery-refresh-resolved"
  ) {
    return { activity: DEFAULT_ACTIVITY, grants: [unknown] };
  }
  return { activity: DEFAULT_ACTIVITY, grants: [ACTIVE_GRANT] };
}

async function installSenderFixture(page: Page, name: string) {
  const state = shareState(name);
  let listReads = 0;
  await page.route(
    `**/api/v1/reports/${DEMO_REPORT_ID}/share**`,
    async (route) => {
      const request = route.request();
      const { pathname } = new URL(request.url());
      const method = request.method();
      if (method === "OPTIONS") {
        await route.fulfill({ status: 204 });
        return;
      }
      if (pathname.endsWith("/activity") && method === "GET") {
        await json(route, { items: state.activity });
        return;
      }
      if (pathname.endsWith(`/share/${GRANT_ID}`) && method === "DELETE") {
        await json(route, { status: "revoked" });
        return;
      }
      if (pathname.endsWith("/share") && method === "GET") {
        listReads += 1;
        const grants =
          name === "share-delivery-refresh-resolved" && listReads > 1
            ? [ACTIVE_GRANT]
            : state.grants;
        await json(route, { items: grants });
        return;
      }
      if (pathname.endsWith("/share") && method === "POST") {
        const body = request.postDataJSON() as Record<string, unknown>;
        const idempotencyKey = request.headers()["idempotency-key"] ?? "";
        if (
          body.recipient_email !== SENDER_RECIPIENT ||
          body.expires_in_days !== 7 ||
          body.max_views !== 25 ||
          Object.keys(body).length !== 3 ||
          idempotencyKey.length < 16
        ) {
          await json(
            route,
            { detail: "Unexpected visual fixture payload" },
            422,
          );
          return;
        }
        await json(route, CREATED_GRANT, 201);
        return;
      }
      await json(
        route,
        { detail: `Unhandled sender fixture: ${method} ${pathname}` },
        404,
      );
    },
  );
}

export function reviewStatus({
  approved = false,
  saved = false,
}: { approved?: boolean; saved?: boolean } = {}) {
  return {
    analysis_id: VISUAL_MATRIX_API_REPORT_ID,
    status: approved ? "approved" : "under_review",
    note: approved
      ? "Counsel review complete and export approved."
      : "Counsel review in progress.",
    reviewer_name: "Visual Counsel",
    reviewer_email: "visual.reviewer@example.invalid",
    reviewed_at: approved ? "2026-07-16T08:47:00.000Z" : null,
    updated_at: "2026-07-14T08:00:00.000Z",
    decision_counts: approved
      ? { accept: 3, reject: 2, edit: 0 }
      : saved
        ? { accept: 0, reject: 1, edit: 0 }
        : { accept: 0, reject: 0, edit: 0 },
    findings_total: 3,
    findings_reviewed: approved ? 3 : saved ? 1 : 0,
    completion_pct: approved ? 100 : saved ? 33.3333 : 0,
  };
}

export const REVIEW_LIFECYCLE_MUTATION_ACK = {
  ...reviewStatus(),
  status: "changes_requested",
  note: VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE,
  reviewer_name: "Pending authoritative refresh",
  reviewer_email: null,
  reviewed_at: "2026-07-17T11:59:00.000Z",
  updated_at: "2026-07-17T11:59:00.000Z",
} as const;

export const REVIEW_LIFECYCLE_REFRESHED_STATUS = {
  ...REVIEW_LIFECYCLE_MUTATION_ACK,
  reviewer_name: "Visual Counsel · authoritative",
  reviewer_email: "visual.reviewer@example.invalid",
  reviewed_at: "2026-07-17T12:00:00.000Z",
  updated_at: "2026-07-17T12:00:00.000Z",
} as const;

export function workspaceSummary({ exportReady = false } = {}) {
  return {
    analysis_id: VISUAL_MATRIX_API_REPORT_ID,
    report_id: API_REPORT.report_id,
    trust_mode: "counsel",
    jurisdiction_bundle: "custom",
    target_jurisdictions: ["US", "EP"],
    jurisdiction_matrix: [
      { jurisdiction: "US", risk: "high", blockers: 2 },
      { jurisdiction: "EP", risk: "medium", blockers: 1 },
    ],
    report_summary: {
      overall_risk: "high",
      blocking_patents_count: 3,
      total_patents_found: 2417,
      executive_summary: "Three material patent families need counsel review.",
    },
    capability_metadata: {
      trust_mode: "counsel",
      capability_profile: "report_grounded",
      routing_profile: {
        modality: "small_molecule",
        matter_type: "fto",
      },
      opinion_readiness: {
        export_ready: exportReady,
      },
      allowed_capabilities: [
        "evidence_search",
        "review_handoff",
        "monitor",
        "export",
      ],
      blocked_capabilities: ["external_live_retrieval"],
      capability_matrix: [],
      tool_policy: {
        execution_mode: "report_grounded_only",
        allowed_actions: [
          "evidence_search",
          "review_handoff",
          "monitor",
          "export",
        ],
        blocked_actions: ["external_live_retrieval"],
        external_retrieval_allowed: false,
        monitoring_actions_allowed: true,
        notes: ["All actions remain bound to retained report evidence."],
      },
      evidence_basis: [],
      system_directives: [
        "Do not present report-grounded screening as a legal opinion.",
      ],
    },
    suggested_evidence_queries: [],
    monitor_seed_defaults: {
      analysis_id: VISUAL_MATRIX_API_REPORT_ID,
      compound_name: "Succinic acid",
      compound_smiles: "OC(=O)CCC(O)=O",
      schedule: "weekly",
      source_report_id: API_REPORT.report_id,
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
      export_ready: exportReady,
      summary: exportReady
        ? "Counsel review is complete and the evidence packet is exportable."
        : "Counsel export remains blocked pending review.",
      jurisdictions_blocking_export: exportReady ? [] : ["US", "EP"],
    },
    data_coverage: {},
    source_convergence: {},
    uncertainty_register: [],
    evidence_scope: {
      mode: "report_evidence",
      external_live_retrieval: false,
      comment_routing_available: true,
      sources_considered: ["Report claims", "Patent citations"],
      governed_note: "Report-grounded evidence only.",
      provider_capabilities: [],
      providers: [],
      hybrid_evidence_ready: false,
    },
  };
}

export function visualMatrixApiContractFixtures() {
  return {
    billingStatus: BILLING_STATUS,
    usage: USAGE,
    invoiceList: INVOICE_LIST,
    creditPackReconciliationApplied: CREDIT_PACK_RECONCILIATION_APPLIED,
    adminUserList: {
      items: [VISUAL_USER],
      total: 1,
      capabilities: ADMIN_CAPABILITIES,
    },
    adminOperation: ADMIN_OPERATION,
    adminOperationList: {
      items: [ADMIN_OPERATION],
      open_total: 1,
      has_more: false,
    },
    ssoStatus: SSO_STATUS,
    ssoStatusActive: SSO_STATUS_ACTIVE,
    apiKeyList: API_KEY_LIST,
    apiKeyListWithItem: API_KEY_LIST_WITH_ITEM,
    commentList: COMMENT_LIST,
    externalSharingPolicy: EXTERNAL_SHARING_POLICY,
    report: API_REPORT,
    claimDecisionMatrixReport: CLAIM_DECISION_MATRIX_REPORT,
    analysis: API_REPORT_ANALYSIS,
    launchedAnalysis: LAUNCHED_ANALYSIS,
    analysisList: ANALYSIS_LIST,
    monitorList: MONITOR_LIST,
    monitorListWithItem: MONITOR_LIST_WITH_ITEM,
    monitorAlertList: MONITOR_ALERT_LIST,
    workspaceSummary: workspaceSummary(),
    reviewStatus: reviewStatus(),
    reviewLifecycleMutationAck: REVIEW_LIFECYCLE_MUTATION_ACK,
    reviewLifecycleRefreshedStatus: REVIEW_LIFECYCLE_REFRESHED_STATUS,
    reviewerDecisionList: REVIEWER_DECISION_LIST,
    savedReviewerDecisionList: {
      items: [SAVED_REVIEWER_DECISION],
      counts: { accept: 0, reject: 1, edit: 0 },
    },
    exportReviewerDecisionList: EXPORT_REVIEWER_DECISION_LIST,
    pendingExportJob: PENDING_EXPORT_JOB,
    completedExportJob: COMPLETED_EXPORT_JOB,
    notificationUnreadCount: NOTIFICATION_UNREAD_COUNT,
    notificationList: NOTIFICATION_LIST,
    notificationPreferences: NOTIFICATION_PREFERENCES,
  } as const;
}

async function installApiProfileFixture(page: Page, name: string) {
  let billingStatusReads = 0;
  let reconciledOperation = false;
  let reviewerDecisionSaved = false;
  let reviewLifecycleTransitioned = false;
  const ledgerReconciled = name === "billing-credit-ledger-reconciled";
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    if (method === "OPTIONS") {
      await route.fulfill({ status: 204 });
      return;
    }

    if (pathname === "/api/v1/billing/status" && method === "GET") {
      billingStatusReads += 1;
      if (name === "billing-stale-data" && billingStatusReads > 1) {
        await json(route, { detail: "Billing status unavailable" }, 503);
        return;
      }
      const blocked = name === "analysis-capacity-blocked";
      await json(route, {
        ...BILLING_STATUS,
        can_manage_billing: name !== "billing-actions-restricted",
        analyses_used: blocked ? 10 : BILLING_STATUS.analyses_used,
        analyses_limit: blocked
          ? 10
          : ledgerReconciled
            ? 17
            : BILLING_STATUS.analyses_limit,
        included_analyses_limit: blocked
          ? 10
          : BILLING_STATUS.included_analyses_limit,
        purchased_credits_balance: blocked
          ? 0
          : ledgerReconciled
            ? CREDIT_PACK_RECONCILIATION_APPLIED.current_purchased_credits_balance
            : BILLING_STATUS.purchased_credits_balance,
      });
      return;
    }
    if (pathname === "/api/v1/billing/usage" && method === "GET") {
      const blocked = name === "analysis-capacity-blocked";
      await json(route, {
        ...USAGE,
        analyses_used: blocked ? 10 : USAGE.analyses_used,
        analyses_limit: blocked
          ? 10
          : ledgerReconciled
            ? 17
            : USAGE.analyses_limit,
        included_analyses_limit: blocked ? 10 : USAGE.included_analyses_limit,
        purchased_credits_balance: blocked
          ? 0
          : ledgerReconciled
            ? CREDIT_PACK_RECONCILIATION_APPLIED.current_purchased_credits_balance
            : USAGE.purchased_credits_balance,
        usage_pct: blocked ? 100 : ledgerReconciled ? 11.8 : USAGE.usage_pct,
      });
      return;
    }
    if (pathname === "/api/v1/billing/invoices" && method === "GET") {
      if (name === "billing-invoice-unavailable") {
        await json(route, { detail: "Invoice history unavailable" }, 503);
        return;
      }
      await json(route, INVOICE_LIST);
      return;
    }
    if (
      pathname === "/api/v1/billing/credit-packs/reconciliation" &&
      method === "GET" &&
      ledgerReconciled
    ) {
      await json(route, CREDIT_PACK_RECONCILIATION_APPLIED);
      return;
    }
    if (
      pathname === "/api/v1/billing/credit-packs/checkout" &&
      method === "POST"
    ) {
      await json(route, { detail: "Checkout provider unavailable" }, 502);
      return;
    }
    if (pathname === "/api/v1/billing/checkout" && method === "POST") {
      if (name === "billing-plan-checkout-failure") {
        await json(route, { detail: "Plan checkout unavailable" }, 502);
        return;
      }
    }
    if (pathname === "/api/v1/billing/portal" && method === "POST") {
      if (name === "billing-portal-failure") {
        await json(route, { detail: "Billing portal unavailable" }, 502);
        return;
      }
    }

    if (pathname === "/api/v1/admin/users" && method === "GET") {
      if (name === "admin-users-restricted") {
        await json(route, { detail: "Forbidden" }, 403);
        return;
      }
      await json(route, {
        items: [
          name === "admin-clerk-authority-unsynchronized"
            ? { ...VISUAL_USER, membership_synchronized: false }
            : name === "admin-users-role-review"
              ? { ...VISUAL_USER, email: "ada@example.com" }
              : VISUAL_USER,
        ],
        total: 1,
        capabilities: ADMIN_CAPABILITIES,
      });
      return;
    }
    if (pathname === "/api/v1/admin/operations" && method === "GET") {
      const operationSurface = name.startsWith("admin-clerk-operation-");
      if (!operationSurface) {
        await json(route, { items: [], open_total: 0, has_more: false });
        return;
      }
      const rejected = name === "admin-clerk-operation-rejected";
      const completed = reconciledOperation;
      await json(route, {
        items: [
          {
            ...ADMIN_OPERATION,
            state: rejected
              ? "failed"
              : completed
                ? "completed"
                : ADMIN_OPERATION.state,
            outcome_confirmed: rejected || completed,
            reconciliation_required: !rejected && !completed,
          },
        ],
        open_total: rejected || completed ? 0 : 1,
        has_more: false,
      });
      return;
    }
    if (pathname.endsWith("/reconcile") && method === "POST") {
      reconciledOperation = true;
      await json(route, {
        ...ADMIN_OPERATION,
        state: "completed",
        outcome_confirmed: true,
        reconciliation_required: false,
      });
      return;
    }

    if (pathname === "/api/v1/admin/sso/status" && method === "GET") {
      await json(
        route,
        name === "settings-sso-active" ? SSO_STATUS_ACTIVE : SSO_STATUS,
      );
      return;
    }
    if (pathname === "/api/v1/admin/sso/configure" && method === "POST") {
      await json(route, { detail: "Identity provider unavailable" }, 503);
      return;
    }
    if (pathname === "/api/v1/api-keys" && method === "GET") {
      await json(
        route,
        name === "settings-api-key-revoke-outcome-unknown"
          ? API_KEY_LIST_WITH_ITEM
          : API_KEY_LIST,
      );
      return;
    }
    if (pathname === "/api/v1/api-keys" && method === "POST") {
      if (name === "settings-api-key-create-outcome-unknown") {
        await json(
          route,
          { detail: "API key creation outcome unavailable" },
          503,
        );
        return;
      }
    }
    if (
      pathname === `/api/v1/api-keys/${VISUAL_MATRIX_API_KEY_ID}` &&
      method === "DELETE"
    ) {
      if (name === "settings-api-key-revoke-outcome-unknown") {
        await json(
          route,
          { detail: "API key revocation outcome unavailable" },
          503,
        );
        return;
      }
      return;
    }
    if (
      pathname === "/api/v1/admin/external-sharing-policy" &&
      method === "GET"
    ) {
      await json(route, EXTERNAL_SHARING_POLICY);
      return;
    }
    if (pathname === "/api/v1/configs/presets" && method === "GET") {
      await json(route, []);
      return;
    }
    if (
      pathname === "/api/v1/analyses" &&
      method === "POST" &&
      name === "analysis-launch-submitted"
    ) {
      await json(route, LAUNCHED_ANALYSIS, 201);
      return;
    }
    if (pathname === "/api/v1/analyses" && method === "GET") {
      if (name === "analyses-load-failure") {
        await json(route, { detail: "Analysis library unavailable" }, 503);
        return;
      }
      await json(route, ANALYSIS_LIST);
      return;
    }
    if (pathname === "/api/v1/monitors" && method === "GET") {
      if (name === "monitors-load-failure") {
        await json(route, { detail: "Monitor workspace unavailable" }, 503);
        return;
      }
      await json(
        route,
        [
          "monitor-pause-outcome-unknown",
          "monitor-delete-outcome-unknown",
          "monitor-alert-dismiss-outcome-unknown",
        ].includes(name)
          ? MONITOR_LIST_WITH_ITEM
          : MONITOR_LIST,
      );
      return;
    }
    if (pathname === "/api/v1/monitors" && method === "POST") {
      if (name === "report-watch-start-outcome-unknown") {
        await json(
          route,
          { detail: "Monitor creation outcome unavailable" },
          503,
        );
        return;
      }
    }
    if (
      pathname === `/api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}` &&
      method === "PATCH"
    ) {
      if (name === "monitor-pause-outcome-unknown") {
        await json(
          route,
          { detail: "Monitor update outcome unavailable" },
          503,
        );
        return;
      }
    }
    if (
      pathname === `/api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}` &&
      method === "DELETE"
    ) {
      if (name === "monitor-delete-outcome-unknown") {
        await json(
          route,
          { detail: "Monitor deletion outcome unavailable" },
          503,
        );
        return;
      }
    }
    if (
      pathname === `/api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}/alerts` &&
      method === "GET"
    ) {
      await json(route, MONITOR_ALERT_LIST);
      return;
    }
    if (
      pathname ===
        `/api/v1/monitors/${VISUAL_MATRIX_MONITOR_ID}/alerts/${VISUAL_MATRIX_MONITOR_ALERT_ID}/dismiss` &&
      method === "POST"
    ) {
      if (name === "monitor-alert-dismiss-outcome-unknown") {
        await json(
          route,
          { detail: "Alert dismissal outcome unavailable" },
          503,
        );
        return;
      }
      return;
    }
    if (pathname === "/api/v1/patents" && method === "GET") {
      if (name === "patents-load-failure") {
        await json(route, { detail: "Patent library unavailable" }, 503);
        return;
      }
    }
    if (pathname === "/api/v1/compounds" && method === "GET") {
      if (name === "compounds-load-failure") {
        await json(route, { detail: "Compound library unavailable" }, 503);
        return;
      }
    }
    if (pathname === "/api/v1/comments/review-queue" && method === "GET") {
      if (name === "reviews-load-failure") {
        await json(route, { detail: "Review queue unavailable" }, 503);
        return;
      }
    }
    if (pathname === "/api/v1/batch" && method === "GET") {
      if (name === "batch-load-failure") {
        await json(route, { detail: "Batch workspace unavailable" }, 503);
        return;
      }
    }

    if (
      pathname === `/api/v1/reports/${VISUAL_MATRIX_API_REPORT_ID}` &&
      method === "GET"
    ) {
      await json(
        route,
        name === "report-claim-decision-source-review"
          ? CLAIM_DECISION_MATRIX_REPORT
          : API_REPORT,
      );
      return;
    }
    if (
      pathname === `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}` &&
      method === "GET"
    ) {
      await json(route, API_REPORT_ANALYSIS);
      return;
    }
    if (
      pathname === `/api/v1/analyses/${VISUAL_MATRIX_LAUNCHED_ANALYSIS_ID}` &&
      method === "GET"
    ) {
      await json(route, LAUNCHED_ANALYSIS);
      return;
    }
    if (
      pathname ===
        `/api/v1/reports/${VISUAL_MATRIX_API_REPORT_ID}/workspace-summary` &&
      method === "GET"
    ) {
      await json(
        route,
        workspaceSummary({ exportReady: name === "report-export-ready" }),
      );
      return;
    }
    if (
      pathname ===
        `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/review-status` &&
      method === "GET"
    ) {
      await json(
        route,
        name === "report-review-lifecycle-transition" &&
          reviewLifecycleTransitioned
          ? REVIEW_LIFECYCLE_REFRESHED_STATUS
          : reviewStatus({
              approved: name === "report-export-ready",
              saved:
                name === "report-review-decision-saved" &&
                reviewerDecisionSaved,
            }),
      );
      return;
    }
    if (
      pathname ===
        `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/review-status` &&
      method === "PUT" &&
      name === "report-review-lifecycle-transition"
    ) {
      const body = request.postDataJSON() as Record<string, unknown>;
      if (
        body.status !== "changes_requested" ||
        body.note !== VISUAL_MATRIX_REVIEW_LIFECYCLE_AUDIT_NOTE ||
        Object.keys(body).length !== 2
      ) {
        await json(route, { detail: "Unexpected lifecycle transition" }, 422);
        return;
      }
      reviewLifecycleTransitioned = true;
      await json(route, REVIEW_LIFECYCLE_MUTATION_ACK);
      return;
    }
    if (
      pathname ===
        `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/decisions` &&
      method === "GET"
    ) {
      await json(
        route,
        name === "report-export-ready"
          ? EXPORT_REVIEWER_DECISION_LIST
          : name === "report-review-decision-saved" && reviewerDecisionSaved
            ? {
                items: [SAVED_REVIEWER_DECISION],
                counts: { accept: 0, reject: 1, edit: 0 },
              }
            : REVIEWER_DECISION_LIST,
      );
      return;
    }
    if (
      pathname ===
        `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/decisions` &&
      method === "POST"
    ) {
      if (name === "review-decision-save-failure") {
        await json(route, { detail: "Reviewer ledger unavailable" }, 503);
        return;
      }
      if (name === "report-review-decision-saved") {
        reviewerDecisionSaved = true;
        await json(route, SAVED_REVIEWER_DECISION, 201);
        return;
      }
    }
    if (
      pathname === `/api/v1/reports/${VISUAL_MATRIX_API_REPORT_ID}/export` &&
      method === "POST" &&
      name === "report-export-ready"
    ) {
      await json(route, PENDING_EXPORT_JOB);
      return;
    }
    if (
      pathname === `/api/v1/exports/${VISUAL_MATRIX_EXPORT_JOB_ID}` &&
      method === "GET" &&
      name === "report-export-ready"
    ) {
      await json(route, COMPLETED_EXPORT_JOB);
      return;
    }
    if (
      pathname === `/api/v1/exports/${VISUAL_MATRIX_EXPORT_JOB_ID}/download` &&
      method === "GET" &&
      name === "report-export-ready"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: COMPLETED_EXPORT_BODY,
      });
      return;
    }
    if (pathname === "/api/v1/comments" && method === "GET") {
      if (name === "report-comments-load-failure") {
        await json(route, { detail: "Comments unavailable" }, 503);
        return;
      }
      await json(
        route,
        [
          "report-comment-post-outcome-unknown",
          "report-resolution-outcome-unknown",
        ].includes(name)
          ? COMMENT_LIST
          : [],
      );
      return;
    }
    if (pathname === "/api/v1/comments" && method === "POST") {
      if (name === "report-comment-post-outcome-unknown") {
        await json(route, { detail: "Comment post outcome unavailable" }, 503);
        return;
      }
    }
    if (
      pathname === `/api/v1/comments/${VISUAL_MATRIX_COMMENT_ID}/resolution` &&
      method === "PATCH"
    ) {
      if (name === "report-resolution-outcome-unknown") {
        await json(route, { detail: "Resolution outcome unavailable" }, 503);
        return;
      }
      return;
    }
    if (pathname === "/api/v1/comments/reviewers" && method === "GET") {
      await json(route, []);
      return;
    }
    if (pathname === "/api/v1/notifications/unread-count" && method === "GET") {
      await json(route, NOTIFICATION_UNREAD_COUNT);
      return;
    }
    if (pathname === "/api/v1/notifications" && method === "GET") {
      await json(route, NOTIFICATION_LIST);
      return;
    }
    if (pathname === "/api/v1/notifications/preferences" && method === "GET") {
      await json(route, NOTIFICATION_PREFERENCES);
      return;
    }
    if (pathname === "/api/v1/notifications/preferences" && method === "PUT") {
      if (name === "settings-notification-save-outcome-unknown") {
        await json(
          route,
          { detail: "Notification save outcome unavailable" },
          503,
        );
        return;
      }
    }
    if (
      pathname === `/api/v1/analyses/${VISUAL_MATRIX_API_REPORT_ID}/chat` &&
      method === "POST"
    ) {
      if (name === "report-chat-failure") {
        await json(route, { detail: "Report chat unavailable" }, 503);
        return;
      }
      if (name === "report-chat-success") {
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "cache-control": "no-cache",
            connection: "keep-alive",
          },
          body: REPORT_CHAT_SUCCESS_STREAM,
        });
        return;
      }
    }

    await json(
      route,
      { detail: `Unhandled visual matrix fixture: ${method} ${pathname}` },
      404,
    );
  });
}

export async function installVisualMatrixStateFixture(
  page: Page,
  name: string,
  profile: "api" | "demo",
) {
  if (profile === "api") {
    await installApiProfileFixture(page, name);
    return;
  }

  if (name === "analysis-failed") {
    await page.route("**/api/v1/analyses/ana_visual_failed", async (route) => {
      await json(route, {
        id: "ana_visual_failed",
        compound_input: "visual failure fixture",
        compound_name: "Visual recovery compound",
        compound_smiles: "CC(=O)O",
        status: "failed",
        current_step: 4,
        progress_pct: 52,
        overall_risk: null,
        blocking_patents_count: 0,
        total_patents_found: 27,
        executive_summary: "",
        estimated_cost_usd: 1.22,
        pipeline_duration_seconds: 412,
        flagged_for_review: true,
        created_at: "2026-07-14T07:00:00.000Z",
        updated_at: "2026-07-14T08:00:00.000Z",
      });
    });
    return;
  }

  if (
    [
      "sender-share-success",
      "share-activity-expanded",
      "share-revoke-confirm",
      "share-delivery-outcome-unknown",
      "share-delivery-outcome-cancel-confirm",
      "share-delivery-refresh-resolved",
      "share-delivery-reconciliation-alert",
      "share-delivery-cancelled-retention",
    ].includes(name)
  ) {
    await installSenderFixture(page, name);
  }
}
