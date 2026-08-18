export type ProductionCompoundCanaryEnvironment = {
  apiProbeURL: string;
  baseURL: string;
  candidateApiOrigin: string;
  launchCompound: string;
  password: string;
  releaseGitSha: string;
  userEmail: string;
};

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const APPROVED_CHEAP_COMPOUNDS = new Set([
  "alendronate",
  "fingolimod",
  "tavaborole",
]);

function requireValue(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for the production compound canary.`);
  }
  return value;
}

function parseProtectedOrigin(value: string, name: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute URL.`);
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parsed.pathname !== "/"
  ) {
    throw new Error(
      `${name} must be one credential-free HTTPS origin without a path, query, or fragment.`,
    );
  }
  if (
    LOCAL_HOSTNAMES.has(parsed.hostname) ||
    parsed.hostname.endsWith(".localhost") ||
    parsed.hostname === "run.app" ||
    parsed.hostname.endsWith(".run.app")
  ) {
    throw new Error(`${name} must target the protected production deployment.`);
  }
  return parsed;
}

function parseApiProbe(value: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_API_PROBE_URL must be an absolute URL.",
    );
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parsed.pathname !== "/api/health/ready" ||
    LOCAL_HOSTNAMES.has(parsed.hostname) ||
    parsed.hostname.endsWith(".localhost") ||
    parsed.hostname === "run.app" ||
    parsed.hostname.endsWith(".run.app")
  ) {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_API_PROBE_URL must be the exact managed-perimeter HTTPS readiness URL.",
    );
  }
  return parsed;
}

export function parseProductionCompoundCanaryEnvironment(
  env: NodeJS.ProcessEnv,
): ProductionCompoundCanaryEnvironment {
  for (const flag of [
    "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
    "NEXT_PUBLIC_DEMO_MODE",
    "PLAYWRIGHT_DEMO_MODE",
  ]) {
    if (env[flag] === "true") {
      throw new Error(`${flag}=true is forbidden in the production canary.`);
    }
  }

  const baseURL = parseProtectedOrigin(
    requireValue(env, "PLAYWRIGHT_PRODUCTION_BASE_URL"),
    "PLAYWRIGHT_PRODUCTION_BASE_URL",
  );
  const allowedOrigin = parseProtectedOrigin(
    requireValue(env, "PLAYWRIGHT_PRODUCTION_ALLOWED_ORIGIN"),
    "PLAYWRIGHT_PRODUCTION_ALLOWED_ORIGIN",
  );
  if (baseURL.origin !== allowedOrigin.origin) {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_BASE_URL does not match the protected production origin allowlist.",
    );
  }
  const apiProbeURL = parseApiProbe(
    requireValue(env, "PLAYWRIGHT_PRODUCTION_API_PROBE_URL"),
  );
  const candidateApiProbeURL = parseApiProbe(
    requireValue(env, "PLAYWRIGHT_PRODUCTION_CANDIDATE_API_PROBE_URL"),
  );
  if (candidateApiProbeURL.origin === apiProbeURL.origin) {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_CANDIDATE_API_PROBE_URL must be isolated from the normal traffic-split API origin.",
    );
  }

  const launchCompound = requireValue(
    env,
    "PLAYWRIGHT_PRODUCTION_LAUNCH_COMPOUND",
  ).toLowerCase();
  if (!APPROVED_CHEAP_COMPOUNDS.has(launchCompound)) {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_LAUNCH_COMPOUND must be an approved inexpensive, ground-truthed canary compound.",
    );
  }

  const releaseGitSha = requireValue(
    env,
    "PLAYWRIGHT_PRODUCTION_RELEASE_GIT_SHA",
  );
  if (!/^[0-9a-f]{40}$/u.test(releaseGitSha)) {
    throw new Error(
      "PLAYWRIGHT_PRODUCTION_RELEASE_GIT_SHA must be the exact 40-character release SHA.",
    );
  }

  return {
    apiProbeURL: apiProbeURL.toString(),
    baseURL: baseURL.toString(),
    candidateApiOrigin: `${candidateApiProbeURL.origin}/`,
    launchCompound,
    password: requireValue(env, "PLAYWRIGHT_PRODUCTION_USER_PASSWORD"),
    releaseGitSha,
    userEmail: requireValue(env, "PLAYWRIGHT_PRODUCTION_USER_EMAIL"),
  };
}
