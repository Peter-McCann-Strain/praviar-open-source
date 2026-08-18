export const DEFAULT_AUTH_RETURN_PATH = "/dashboard";

const LOCAL_ORIGIN = "https://praviar.local";
const AUTH_RETURN_PATH_MAX_LENGTH = 2048;
const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001F\u007F]/;
const SENSITIVE_RETURN_QUERY_KEYS = new Set([
  "canonicalsmiles",
  "cas",
  "casnumber",
  "compound",
  "compoundinput",
  "inchi",
  "inchikey",
  "smiles",
]);

function normalizedQueryKey(key: string): string {
  return key.replace(/[^a-z0-9]/giu, "").toLowerCase();
}

function containsSensitiveAssignment(value: string, depth = 0): boolean {
  if (depth > 3) return false;

  let candidate = value;

  for (let decodePass = depth; decodePass <= 3; decodePass += 1) {
    const parameterSegments = new Set([candidate]);

    // Nested return targets commonly prefix their first parameter with a path
    // (for example, `/analyses/new?compound=...`). Inspect every query/hash
    // suffix so the path cannot disguise the sensitive key.
    for (let index = 0; index < candidate.length; index += 1) {
      if (candidate[index] === "?" || candidate[index] === "#") {
        parameterSegments.add(candidate.slice(index + 1));
      }
    }

    for (const segment of parameterSegments) {
      const params = new URLSearchParams(segment.replace(/^[?#]+/u, ""));

      for (const [key, parameterValue] of params.entries()) {
        if (SENSITIVE_RETURN_QUERY_KEYS.has(normalizedQueryKey(key))) {
          return true;
        }

        if (
          depth < 3 &&
          parameterValue !== segment &&
          containsSensitiveAssignment(parameterValue, depth + 1)
        ) {
          return true;
        }
      }
    }

    try {
      const decoded = decodeURIComponent(candidate);
      if (decoded === candidate) break;
      candidate = decoded;
    } catch {
      break;
    }
  }

  return false;
}

function stripSensitiveReturnQuery(url: URL): void {
  for (const key of [...url.searchParams.keys()]) {
    const normalizedKey = normalizedQueryKey(key);
    const values = url.searchParams.getAll(key);
    if (
      SENSITIVE_RETURN_QUERY_KEYS.has(normalizedKey) ||
      values.some(containsSensitiveAssignment)
    ) {
      url.searchParams.delete(key);
    }
  }
}

function stripSensitiveReturnFragment(url: URL): void {
  if (url.hash && containsSensitiveAssignment(url.hash)) {
    url.hash = "";
  }
}

export function resolveAuthReturnPath(value: string | null): string {
  const candidate = value?.trim();

  if (
    !candidate ||
    candidate.length > AUTH_RETURN_PATH_MAX_LENGTH ||
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    CONTROL_CHARACTER_PATTERN.test(candidate)
  ) {
    return DEFAULT_AUTH_RETURN_PATH;
  }

  try {
    const url = new URL(candidate, LOCAL_ORIGIN);

    if (url.origin !== LOCAL_ORIGIN) {
      return DEFAULT_AUTH_RETURN_PATH;
    }

    stripSensitiveReturnQuery(url);
    stripSensitiveReturnFragment(url);

    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return DEFAULT_AUTH_RETURN_PATH;
  }
}

export function resolveExplicitAuthReturnPath(
  value: string | null,
): string | null {
  const returnPath = resolveAuthReturnPath(value);
  return returnPath === DEFAULT_AUTH_RETURN_PATH ? null : returnPath;
}
