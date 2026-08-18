import { API_BASE_URL } from "./constants";
import { getAuthBoundarySignal, isAuthTokenAccepted } from "./auth-events";
import { logError } from "./error-logger";
import { canonicalProblemTypeUri } from "./problem-types";

/** Default request timeout in milliseconds (30 seconds). */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Maximum number of retries for 5xx server errors and 429 rate limits. */
const DEFAULT_MAX_RETRIES = 3;

/** Base delay in ms for exponential backoff (doubles each retry). */
const RETRY_BASE_DELAY_MS = 500;

/** Maximum Retry-After delay we will honour (30 seconds). */
const MAX_RETRY_AFTER_MS = 30_000;

const PUBLIC_API_PATH_PREFIXES = ["/public-reference"] as const;

export interface APIErrorTelemetry {
  status: number;
  errorClass: "APIError";
  typeUri?: string;
  requestId?: string;
  correlationId?: string;
}

class APIError extends Error {
  public readonly telemetry: APIErrorTelemetry;

  constructor(
    public status: number,
    message: string,
    public data?: unknown,
    telemetry: Omit<APIErrorTelemetry, "status" | "errorClass"> = {},
  ) {
    super(message);
    this.name = "APIError";
    this.telemetry = {
      ...telemetry,
      status,
      errorClass: "APIError",
    };
  }
}

export { APIError };

export function isAuthBoundaryError(error: unknown): error is APIError {
  if (error instanceof APIError) {
    return error.status === 401 || error.status === 403;
  }
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return status === 401 || status === 403;
  }
  return false;
}

interface ApiClientOptions<T = unknown> extends Omit<RequestInit, "signal"> {
  token?: string;
  /** Request timeout in ms. Defaults to 30s. Set to 0 to disable. */
  timeout?: number;
  /** External AbortSignal (e.g. from TanStack Query). Merged with timeout signal. */
  signal?: AbortSignal;
  /** Max retries on 5xx errors. Defaults to 3. Set to 0 to disable. */
  maxRetries?: number;
  /**
   * Optional runtime validator. If provided, the parsed JSON is passed through
   * this function before being returned. Throw or return a typed value.
   * Example: `validate: (d) => MyZodSchema.parse(d)`
   */
  validate?: (data: unknown) => T;
}

interface ApiErrorBody {
  detail?: string;
  type?: unknown;
  request_id?: unknown;
  correlation_id?: unknown;
  [key: string]: unknown;
}

const CORRELATION_ID_SHAPE = /^[A-Za-z0-9._-]{1,128}$/u;
/** Returns true for status codes that should trigger a retry. */
function isRetryableStatus(status: number): boolean {
  return status === 429 || (status >= 500 && status < 600);
}

/** Parse the Retry-After header and return a delay in ms, capped at MAX_RETRY_AFTER_MS. */
function parseRetryAfterMs(response: Response): number {
  const header = response.headers.get("Retry-After");
  if (!header) return 0;
  const seconds = parseInt(header, 10);
  if (!Number.isNaN(seconds) && seconds > 0) {
    return Math.min(seconds * 1000, MAX_RETRY_AFTER_MS);
  }
  // HTTP-date form: e.g. "Fri, 31 Dec 1999 23:59:59 GMT"
  const retryAt = Date.parse(header);
  if (!Number.isNaN(retryAt)) {
    const delayMs = retryAt - Date.now();
    if (delayMs > 0) return Math.min(delayMs, MAX_RETRY_AFTER_MS);
  }
  return 0;
}

function isPublicApiPath(path: string): boolean {
  return PUBLIC_API_PATH_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

/** Sleep for the given number of milliseconds, respecting an abort signal. */
function retrySleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

async function parseErrorBody(
  response: Response,
): Promise<ApiErrorBody | null> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
  const trimmed = text.trim();
  const looksJson =
    contentType.includes("application/json") ||
    trimmed.startsWith("{") ||
    trimmed.startsWith("[");

  if (!looksJson) {
    return { detail: trimmed };
  }

  try {
    return JSON.parse(text) as ApiErrorBody;
  } catch {
    logError(new Error("API error response could not be parsed"), {
      source: "apiClient",
      extra: { action: "parse_error_response", status: response.status },
    });
    return { detail: trimmed };
  }
}

function safeApiErrorMessage(status: number): string {
  if (status === 401) return "Authentication is required.";
  if (status === 403) {
    return "You do not have permission to complete this request.";
  }
  if (status === 404) return "The requested resource was not found.";
  if (status === 410) return "The requested resource is no longer available.";
  if (status === 409) return "The request conflicts with the current state.";
  if (status === 413) return "The submitted content is too large.";
  if (status === 415) return "The submitted content type is not supported.";
  if (status === 422) return "Some submitted information is invalid.";
  if (status === 429) return "Too many requests. Please try again shortly.";
  if (status >= 500) {
    return "The service is temporarily unavailable. Please try again.";
  }
  return "The request could not be completed.";
}

function safeCorrelationId(value: unknown): string | undefined {
  return typeof value === "string" && CORRELATION_ID_SHAPE.test(value)
    ? value
    : undefined;
}

function buildApiErrorTelemetry(
  response: Response,
  data: ApiErrorBody | null,
): APIErrorTelemetry {
  const requestId =
    safeCorrelationId(response.headers.get("X-Request-ID")) ??
    safeCorrelationId(data?.request_id);
  const correlationId =
    safeCorrelationId(response.headers.get("X-Correlation-ID")) ??
    safeCorrelationId(data?.correlation_id);
  const typeUri = canonicalProblemTypeUri(data?.type);
  return {
    status: response.status,
    errorClass: "APIError",
    ...(typeUri ? { typeUri } : {}),
    ...(requestId ? { requestId } : {}),
    ...(correlationId ? { correlationId } : {}),
  };
}

function buildSafeApiErrorData(
  telemetry: APIErrorTelemetry,
): Record<string, string> | undefined {
  const data: Record<string, string> = {};
  if (telemetry.typeUri) data.type = telemetry.typeUri;
  if (telemetry.requestId) data.request_id = telemetry.requestId;
  if (telemetry.correlationId) data.correlation_id = telemetry.correlationId;
  return Object.keys(data).length > 0 ? data : undefined;
}

function linkAbortSignal(
  source: AbortSignal,
  target: AbortController,
): () => void {
  if (source.aborted) {
    target.abort(source.reason);
    return () => {};
  }
  const handleAbort = () => target.abort(source.reason);
  source.addEventListener("abort", handleAbort, { once: true });
  return () => source.removeEventListener("abort", handleAbort);
}

function assertAuthBoundaryStillCurrent(token: string | undefined): void {
  if (token && !isAuthTokenAccepted(token)) {
    throw new Error("Authentication boundary changed");
  }
}

export async function apiClient<T>(
  path: string,
  options: ApiClientOptions<T> = {},
): Promise<T> {
  const {
    token,
    timeout = DEFAULT_TIMEOUT_MS,
    signal: externalSignal,
    maxRetries = DEFAULT_MAX_RETRIES,
    validate,
    ...fetchOptions
  } = options;
  if (!API_BASE_URL) {
    throw new Error("API client is unavailable without NEXT_PUBLIC_API_URL");
  }
  if (!token && !isPublicApiPath(path)) {
    throw new APIError(401, "Authentication required for private endpoints");
  }
  const url = `${API_BASE_URL}/api/v1${path}`;

  const headers = new Headers(fetchOptions.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  assertAuthBoundaryStillCurrent(token);

  // Merge timeout + external signal via AbortController
  const controller = new AbortController();
  const abortSignalCleanups: Array<() => void> = [];
  const timeoutId =
    timeout > 0
      ? setTimeout(
          () =>
            controller.abort(new Error(`Request timed out after ${timeout}ms`)),
          timeout,
        )
      : undefined;

  if (externalSignal) {
    abortSignalCleanups.push(linkAbortSignal(externalSignal, controller));
  }
  if (token) {
    abortSignalCleanups.push(
      linkAbortSignal(getAuthBoundarySignal(), controller),
    );
  }

  // Only retry GET/HEAD by default; mutations are not idempotent
  const method = (fetchOptions.method ?? "GET").toUpperCase();
  const isIdempotent = method === "GET" || method === "HEAD";
  const effectiveMaxRetries = isIdempotent ? maxRetries : 0;

  let lastError: APIError | null = null;
  // Set when the previous attempt already slept for a server-provided
  // Retry-After. In that case we must not also apply the client backoff for
  // this attempt, or the caller waits Retry-After + backoff (double delay).
  let honouredRetryAfter = false;

  try {
    if (controller.signal.aborted) {
      throw controller.signal.reason;
    }

    for (let attempt = 0; attempt <= effectiveMaxRetries; attempt++) {
      assertAuthBoundaryStillCurrent(token);

      // Wait before retrying (skip on first attempt, and skip when the prior
      // attempt already honoured a Retry-After header).
      if (attempt > 0 && !honouredRetryAfter) {
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
        const jitter = delay * 0.1 * Math.random();
        await retrySleep(delay + jitter, controller.signal);
        assertAuthBoundaryStillCurrent(token);
      }
      honouredRetryAfter = false;

      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });
      assertAuthBoundaryStillCurrent(token);

      if (!response.ok) {
        const data = await parseErrorBody(response);
        assertAuthBoundaryStillCurrent(token);
        const telemetry = buildApiErrorTelemetry(response, data);

        lastError = new APIError(
          response.status,
          safeApiErrorMessage(response.status),
          buildSafeApiErrorData(telemetry),
          telemetry,
        );

        // Retry on 5xx and 429 (rate-limited) if attempts remain
        if (
          isRetryableStatus(response.status) &&
          attempt < effectiveMaxRetries
        ) {
          // For 429, honour the Retry-After header instead of the client
          // backoff for the next attempt (the flag suppresses the top-of-loop
          // backoff so we wait exactly Retry-After, not Retry-After + backoff).
          if (response.status === 429) {
            const retryAfterMs = parseRetryAfterMs(response);
            if (retryAfterMs > 0) {
              await retrySleep(retryAfterMs, controller.signal);
              assertAuthBoundaryStillCurrent(token);
              honouredRetryAfter = true;
            }
          }
          continue;
        }

        throw lastError;
      }

      if (response.status === 204) return undefined as T;
      const data: unknown = await response.json();
      assertAuthBoundaryStillCurrent(token);
      return validate ? validate(data) : (data as T);
    }

    // Should not be reachable, but satisfy TypeScript
    throw lastError ?? new APIError(500, "Unexpected retry loop exit");
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    for (const cleanup of abortSignalCleanups) {
      cleanup();
    }
  }
}
