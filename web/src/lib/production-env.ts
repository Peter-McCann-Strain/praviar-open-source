type RuntimeEnv = {
  nodeEnv?: string;
};

type ClerkRuntimeEnv = RuntimeEnv & {
  clerkPublishableKey?: string;
  clerkSecretKey?: string;
  requireSecret?: boolean;
  runtimePhase?: string;
};

type AppUrlRuntimeEnv = RuntimeEnv & {
  appUrl?: string;
};

type ApiUrlRuntimeEnv = RuntimeEnv & {
  apiUrl?: string;
  required?: boolean;
};

type MissingClerkBypassEnv = RuntimeEnv & {
  demoMode?: string;
  devAuthBypass?: string;
};

function decodeBase64(value: string): string | null {
  try {
    return globalThis.atob(value);
  } catch {
    return null;
  }
}

export function hasValidClerkPublishableKey(
  value: string | undefined,
): boolean {
  if (typeof value !== "string") {
    return false;
  }

  const parts = value.split("_");
  if (
    parts.length !== 3 ||
    parts[0] !== "pk" ||
    !["test", "live"].includes(parts[1]) ||
    !parts[2]
  ) {
    return false;
  }

  const decoded = decodeBase64(parts[2]);
  if (!decoded?.endsWith("$")) {
    return false;
  }

  const frontendApi = decoded.slice(0, -1);
  return frontendApi.includes(".") && !frontendApi.includes("$");
}

export function hasValidClerkSecretKey(value: string | undefined): boolean {
  return typeof value === "string" && value.startsWith("sk_");
}

function normalizeHostname(value: string): string {
  return value
    .toLowerCase()
    .replace(/^\[/u, "")
    .replace(/\]$/u, "")
    .replace(/\.$/u, "");
}

function parseIpv4Octets(
  hostname: string,
): [number, number, number, number] | null {
  const segments = hostname.split(".");
  const octets = segments.map(Number);
  if (
    octets.length !== 4 ||
    octets.some(
      (octet, index) =>
        !Number.isInteger(octet) ||
        octet < 0 ||
        octet > 255 ||
        String(octet) !== segments[index],
    )
  ) {
    return null;
  }

  return octets as [number, number, number, number];
}

function isPrivateOrLocalIpv4(hostname: string): boolean {
  const octets = parseIpv4Octets(hostname);
  if (!octets) return false;

  const [first, second] = octets;
  return (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

function mappedIpv4Address(hostname: string): string | null {
  const match = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/u.exec(hostname);
  if (!match) return null;

  const upper = Number.parseInt(match[1]!, 16);
  const lower = Number.parseInt(match[2]!, 16);
  return [upper >> 8, upper & 0xff, lower >> 8, lower & 0xff].join(".");
}

function isIpLiteral(value: string): boolean {
  const hostname = normalizeHostname(value);
  return parseIpv4Octets(hostname) !== null || hostname.includes(":");
}

function isLocalHostname(value: string): boolean {
  const hostname = normalizeHostname(value);
  const isIpv6Literal = hostname.includes(":");
  const mappedIpv4 = mappedIpv4Address(hostname);
  return (
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname.endsWith(".local") ||
    (isIpv6Literal &&
      (hostname === "::" ||
        hostname === "::1" ||
        hostname.startsWith("fe80:") ||
        hostname.startsWith("fc") ||
        hostname.startsWith("fd") ||
        (mappedIpv4 !== null && isPrivateOrLocalIpv4(mappedIpv4)))) ||
    hostname === "0.0.0.0" ||
    isPrivateOrLocalIpv4(hostname)
  );
}

function usesLocalHost(value: string): boolean {
  try {
    const { hostname } = new URL(value);
    return isLocalHostname(hostname);
  } catch {
    return /(?:localhost|127\.0\.0\.1|\[?::1\]?|0\.0\.0\.0)/i.test(value);
  }
}

function parseHttpOrigin(value: string, variableName: string): URL {
  if (value !== value.trim()) {
    throw new Error(`${variableName} must not contain surrounding whitespace.`);
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${variableName} must be an absolute HTTP(S) URL.`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`${variableName} must use HTTP or HTTPS.`);
  }
  if (parsed.username || parsed.password) {
    throw new Error(`${variableName} must not contain credentials.`);
  }
  if (parsed.hostname.endsWith(".")) {
    throw new Error(`${variableName} must use a canonical hostname.`);
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error(
      `${variableName} must be an origin without a path, query, or fragment.`,
    );
  }

  return parsed;
}

/**
 * Validate and canonicalise the public API URL before it reaches fetch or CSP.
 *
 * Non-production development may use an HTTP loopback origin. Production must
 * use a remote HTTPS origin, and an explicitly required value cannot be absent.
 */
export function resolvePublicApiOrigin({
  apiUrl,
  nodeEnv,
  required = false,
}: ApiUrlRuntimeEnv): string | null {
  if (!apiUrl) {
    if (required) {
      throw new Error("NEXT_PUBLIC_API_URL is required in production.");
    }
    return null;
  }

  const parsed = parseHttpOrigin(apiUrl, "NEXT_PUBLIC_API_URL");
  if (nodeEnv === "production") {
    if (parsed.protocol !== "https:") {
      throw new Error("NEXT_PUBLIC_API_URL must use HTTPS in production.");
    }
    if (isIpLiteral(parsed.hostname)) {
      throw new Error(
        "NEXT_PUBLIC_API_URL must use a DNS hostname, not an IP address, in production.",
      );
    }
    if (isLocalHostname(parsed.hostname)) {
      throw new Error(
        "NEXT_PUBLIC_API_URL must not target a local or private host in production.",
      );
    }
  }

  return parsed.origin;
}

/** Validate a Clerk custom domain as a single canonical DNS hostname. */
export function resolveClerkDomain(value: string | undefined): string | null {
  if (!value) return null;
  if (value !== value.trim() || value.includes("://")) {
    throw new Error(
      "NEXT_PUBLIC_CLERK_DOMAIN must be a hostname without a scheme or whitespace.",
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(`https://${value}`);
  } catch {
    throw new Error("NEXT_PUBLIC_CLERK_DOMAIN must be a valid hostname.");
  }

  const hostname = normalizeHostname(parsed.hostname);
  const labels = hostname.split(".");
  const validDnsName =
    hostname.length <= 253 &&
    labels.length >= 2 &&
    labels.every(
      (label) =>
        label.length >= 1 &&
        label.length <= 63 &&
        /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/u.test(label),
    );

  if (
    parsed.username ||
    parsed.password ||
    parsed.port ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash ||
    parsed.hostname.endsWith(".") ||
    isLocalHostname(hostname) ||
    parseIpv4Octets(hostname) !== null ||
    !validDnsName
  ) {
    throw new Error(
      "NEXT_PUBLIC_CLERK_DOMAIN must be a non-local DNS hostname without credentials, port, path, query, or fragment.",
    );
  }

  return hostname;
}

export function allowsMissingClerkProtectedRouteBypass({
  demoMode,
  devAuthBypass,
  nodeEnv,
}: MissingClerkBypassEnv): boolean {
  if (nodeEnv === "production") {
    return false;
  }
  return demoMode === "true" || devAuthBypass === "true";
}

export function assertClerkConfiguredForProduction({
  clerkPublishableKey,
  clerkSecretKey,
  nodeEnv,
  requireSecret = false,
  runtimePhase,
}: ClerkRuntimeEnv): void {
  if (nodeEnv !== "production") {
    return;
  }
  if (!hasValidClerkPublishableKey(clerkPublishableKey)) {
    throw new Error(
      "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY must be set in production.",
    );
  }
  if (
    requireSecret &&
    runtimePhase !== "phase-production-build" &&
    !hasValidClerkSecretKey(clerkSecretKey)
  ) {
    throw new Error("CLERK_SECRET_KEY must be set in production.");
  }
}

export function assertAppUrlConfiguredForProduction({
  appUrl,
  nodeEnv,
}: AppUrlRuntimeEnv): void {
  if (nodeEnv !== "production") {
    return;
  }
  if (!appUrl) {
    throw new Error(
      "NEXT_PUBLIC_APP_URL is required in production. Set it to the deployment's canonical HTTPS origin.",
    );
  }
  if (usesLocalHost(appUrl)) {
    throw new Error(
      "NEXT_PUBLIC_APP_URL must not target local hosts in production.",
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(appUrl);
  } catch {
    throw new Error(
      "NEXT_PUBLIC_APP_URL must be an absolute URL in production.",
    );
  }
  if (parsed.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_APP_URL must use HTTPS in production.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("NEXT_PUBLIC_APP_URL must not contain credentials.");
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error(
      "NEXT_PUBLIC_APP_URL must be an origin without a path, query, or fragment.",
    );
  }
}

export function resolveAppUrl({ appUrl, nodeEnv }: AppUrlRuntimeEnv): string {
  assertAppUrlConfiguredForProduction({ appUrl, nodeEnv });
  const candidate = appUrl ?? "http://localhost:3000";

  try {
    return new URL(candidate).origin;
  } catch {
    throw new Error("NEXT_PUBLIC_APP_URL must be an absolute URL.");
  }
}
