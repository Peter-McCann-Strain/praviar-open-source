export type ResourceFailure = {
  currentUrl: string;
  errorText?: string;
  expectedReplacementUrl?: string;
  isNavigationRequest: boolean;
  requestUrl: string;
  resourceType: string;
};

export function isAllowedConsoleError(
  message: string,
  allowedPrefixes: readonly string[],
): boolean {
  return allowedPrefixes.some((prefix) => message.startsWith(prefix));
}

const FRAMEWORK_WARNING_PATTERN =
  /hydration|hydrated but some attributes|not wrapped in act|react does not recognize|incorrect casing|unrecognized in this browser|missing `description`|content security policy|refused to (?:load|execute)|minified react error/iu;

export function isFatalConsoleDiagnostic({
  allowedErrorPrefixes,
  allowedWarningPrefixes,
  message,
  type,
}: {
  allowedErrorPrefixes: readonly string[];
  allowedWarningPrefixes: readonly string[];
  message: string;
  type: string;
}): boolean {
  if (type !== "error" && type !== "warning") return false;
  if (FRAMEWORK_WARNING_PATTERN.test(message)) return true;
  const allowedPrefixes =
    type === "error" ? allowedErrorPrefixes : allowedWarningPrefixes;
  return !isAllowedConsoleError(message, allowedPrefixes);
}

export function isProvenBenignNavigationReplacement({
  currentUrl,
  errorText,
  expectedReplacementUrl,
  isNavigationRequest,
  requestUrl,
  resourceType,
}: ResourceFailure): boolean {
  return (
    errorText === "net::ERR_ABORTED" &&
    isNavigationRequest &&
    resourceType === "document" &&
    currentUrl !== "about:blank" &&
    currentUrl !== requestUrl &&
    expectedReplacementUrl !== undefined &&
    currentUrl === expectedReplacementUrl
  );
}

export function assertStrongHsts(
  header: string | undefined,
  minimumMaxAge = 31_536_000,
  requireIncludeSubDomains = true,
): void {
  if (!header) throw new Error("Strict-Transport-Security header is missing");
  const directives = header
    .split(";")
    .map((directive) => directive.trim())
    .filter(Boolean);
  const seenDirectives = new Set<string>();
  let maxAge: number | undefined;
  let hasIncludeSubDomains = false;
  for (const directive of directives) {
    const name = directive.split("=", 1)[0]?.trim().toLowerCase();
    if (!name)
      throw new Error("Strict-Transport-Security contains an empty directive");
    if (seenDirectives.has(name)) {
      throw new Error(`Strict-Transport-Security contains duplicate ${name}`);
    }
    seenDirectives.add(name);
    if (name === "max-age") {
      const match = /^max-age\s*=\s*(\d+)$/iu.exec(directive);
      if (!match) {
        throw new Error("Strict-Transport-Security max-age is malformed");
      }
      maxAge = Number(match[1]);
    } else if (name === "includesubdomains") {
      if (!/^includeSubDomains$/iu.test(directive)) {
        throw new Error(
          "Strict-Transport-Security includeSubDomains is malformed",
        );
      }
      hasIncludeSubDomains = true;
    }
  }
  const maxAgeValue = maxAge ?? Number.NaN;
  if (!Number.isSafeInteger(maxAgeValue) || maxAgeValue < minimumMaxAge) {
    throw new Error(
      `Strict-Transport-Security max-age must be at least ${minimumMaxAge}`,
    );
  }
  if (requireIncludeSubDomains && !hasIncludeSubDomains) {
    throw new Error("Strict-Transport-Security must include includeSubDomains");
  }
}

export function parseCspDirectives(csp: string): Map<string, string[]> {
  const directives = new Map<string, string[]>();
  for (const rawDirective of csp.split(";")) {
    const tokens = rawDirective.trim().split(/\s+/u).filter(Boolean);
    const [name, ...values] = tokens;
    if (!name) continue;
    if (directives.has(name)) {
      throw new Error(`Duplicate CSP directive: ${name}`);
    }
    directives.set(name, values);
  }
  return directives;
}
