export const CRITICAL_STAGING_JOURNEY_ACTIONS = [
  "sign_in",
  "sso_callback_route",
  "billing_backend_checkout_created",
  "billing_simulated_return_reconciled",
  "setup_readiness_loaded",
  "analysis_launch",
  "analysis_terminal_completed",
  "launched_report_open",
  "launched_report_visual_receipts",
  "export_blocked_before_review",
  "reviewer_findings_decided",
  "report_review_approved",
  "review_flag",
  "analysis_cleanup",
  "export_complete",
  "export_download",
  "export_cleanup",
  "recipient_grant_create",
  "recipient_verification_gate_open",
  "recipient_grant_revoke_cleanup",
] as const;

export type CriticalStagingJourneyAction =
  (typeof CRITICAL_STAGING_JOURNEY_ACTIONS)[number];

export type StagingAnalysisPollDecision = "wait" | "complete";

export type StagingJourneyEnvironment = {
  baseURL: string;
  launchCompound: string;
  password: string;
  shareRecipientEmail: string;
  stripeBoundaryMode: "mock-return";
  userEmail: string;
};

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const SAFE_STAGING_COMPOUNDS = new Set([
  "alendronate",
  "fingolimod",
  "tavaborole",
]);
const TERMINAL_ANALYSIS_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "deleted",
]);

export function classifyStagingAnalysisStatus(
  status: unknown,
): StagingAnalysisPollDecision {
  if (status === "completed") return "complete";
  if (status === "pending" || status === "running") return "wait";
  if (typeof status === "string" && TERMINAL_ANALYSIS_STATUSES.has(status)) {
    throw new Error(
      `Newly launched analysis reached terminal status ${status}.`,
    );
  }
  throw new Error(
    `Newly launched analysis returned unsupported status ${
      typeof status === "string" ? status : "invalid"
    }.`,
  );
}

function requireValue(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(
      `${name} is required for the staging critical-journey gate.`,
    );
  }
  return value;
}

export function parseStagingJourneyEnvironment(
  env: NodeJS.ProcessEnv,
): StagingJourneyEnvironment {
  for (const flag of [
    "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
    "NEXT_PUBLIC_DEMO_MODE",
    "PLAYWRIGHT_DEMO_MODE",
  ]) {
    if (env[flag] === "true") {
      throw new Error(
        `${flag}=true is forbidden in the staging critical-journey gate.`,
      );
    }
  }

  const baseURL = requireValue(env, "PLAYWRIGHT_STAGING_BASE_URL");
  const allowedOrigin = requireValue(env, "PLAYWRIGHT_STAGING_ALLOWED_ORIGIN");
  let parsedBaseURL: URL;
  try {
    parsedBaseURL = new URL(baseURL);
  } catch {
    throw new Error("PLAYWRIGHT_STAGING_BASE_URL must be an absolute URL.");
  }
  if (parsedBaseURL.protocol !== "https:") {
    throw new Error("PLAYWRIGHT_STAGING_BASE_URL must use https.");
  }
  if (
    parsedBaseURL.username ||
    parsedBaseURL.password ||
    parsedBaseURL.search ||
    parsedBaseURL.hash ||
    parsedBaseURL.pathname !== "/"
  ) {
    throw new Error(
      "PLAYWRIGHT_STAGING_BASE_URL must be a credential-free origin without a path, query, or fragment.",
    );
  }
  if (
    LOCAL_HOSTNAMES.has(parsedBaseURL.hostname) ||
    parsedBaseURL.hostname.endsWith(".localhost")
  ) {
    throw new Error(
      "PLAYWRIGHT_STAGING_BASE_URL must target a remote production-shaped deployment.",
    );
  }
  let parsedAllowedOrigin: URL;
  try {
    parsedAllowedOrigin = new URL(allowedOrigin);
  } catch {
    throw new Error(
      "PLAYWRIGHT_STAGING_ALLOWED_ORIGIN must be an absolute URL.",
    );
  }
  if (
    parsedAllowedOrigin.protocol !== "https:" ||
    parsedAllowedOrigin.username ||
    parsedAllowedOrigin.password ||
    parsedAllowedOrigin.search ||
    parsedAllowedOrigin.hash ||
    parsedAllowedOrigin.pathname !== "/"
  ) {
    throw new Error(
      "PLAYWRIGHT_STAGING_ALLOWED_ORIGIN must be one credential-free HTTPS origin.",
    );
  }
  if (parsedBaseURL.origin !== parsedAllowedOrigin.origin) {
    throw new Error(
      "PLAYWRIGHT_STAGING_BASE_URL does not match the protected staging origin allowlist.",
    );
  }
  const stripeBoundaryMode = requireValue(
    env,
    "PLAYWRIGHT_STAGING_STRIPE_BOUNDARY_MODE",
  );
  if (stripeBoundaryMode !== "mock-return") {
    throw new Error(
      "PLAYWRIGHT_STAGING_STRIPE_BOUNDARY_MODE must be mock-return; live payment completion is forbidden in this gate.",
    );
  }
  const launchCompound = requireValue(
    env,
    "PLAYWRIGHT_STAGING_LAUNCH_COMPOUND",
  ).toLowerCase();
  if (!SAFE_STAGING_COMPOUNDS.has(launchCompound)) {
    throw new Error(
      "PLAYWRIGHT_STAGING_LAUNCH_COMPOUND must be one of the approved inexpensive, ground-truthed release-gate compounds.",
    );
  }

  return {
    baseURL: parsedBaseURL.toString(),
    launchCompound,
    password: requireValue(env, "PLAYWRIGHT_STAGING_USER_PASSWORD"),
    shareRecipientEmail: requireValue(
      env,
      "PLAYWRIGHT_STAGING_SHARE_RECIPIENT_EMAIL",
    ),
    stripeBoundaryMode,
    userEmail: requireValue(env, "PLAYWRIGHT_STAGING_USER_EMAIL"),
  };
}

export function createCriticalJourneyLedger() {
  const completed = new Set<CriticalStagingJourneyAction>();

  return {
    mark(action: CriticalStagingJourneyAction) {
      if (completed.has(action)) {
        throw new Error(
          `Critical staging action was recorded twice: ${action}`,
        );
      }
      completed.add(action);
    },
    assertComplete() {
      const missing = CRITICAL_STAGING_JOURNEY_ACTIONS.filter(
        (action) => !completed.has(action),
      );
      if (missing.length > 0) {
        throw new Error(
          `Staging critical-journey gate did not execute: ${missing.join(", ")}`,
        );
      }
    },
    snapshot() {
      return CRITICAL_STAGING_JOURNEY_ACTIONS.filter((action) =>
        completed.has(action),
      );
    },
  };
}
