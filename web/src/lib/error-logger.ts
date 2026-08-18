/**
 * Centralized error logging with optional Sentry integration.
 *
 * Set NEXT_PUBLIC_SENTRY_DSN to enable remote error reporting.
 * When DSN is absent, errors are logged to console only.
 */

import {
  sanitizeDiagnosticMetadata,
  sanitizeDiagnosticText,
} from "@/lib/diagnostic-redaction";
import { canonicalProblemTypeUri } from "@/lib/problem-types";

interface ErrorContext {
  /** Where the error occurred (component name, hook, etc.) */
  source?: string;
  /** Additional structured metadata */
  extra?: Record<string, unknown>;
  /** User ID for attribution */
  userId?: string;
  /** Severity level override */
  level?: "fatal" | "error" | "warning" | "info";
}

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;
type SentryModule = typeof import("@sentry/browser");
let sentryModulePromise: Promise<SentryModule> | null = null;
const CORRELATION_ID_SHAPE = /^[A-Za-z0-9._-]{1,128}$/u;

interface SafeApiErrorTelemetry {
  status: number;
  errorClass: "APIError";
  typeUri?: string;
  requestId?: string;
  correlationId?: string;
}

function loadSentry(): Promise<SentryModule> {
  sentryModulePromise ??= import("@sentry/browser");
  return sentryModulePromise;
}

/**
 * Initialize error reporting. Call once at app startup.
 * Sentry is initialized via sentry.*.config.ts files when DSN is set.
 */
export async function initErrorReporting(): Promise<void> {
  if (SENTRY_DSN) {
    const Sentry = await loadSentry();
    Sentry.init({
      dsn: SENTRY_DSN,
      tracesSampleRate: 0.1,
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: 1.0,
      environment: process.env.NODE_ENV,
    });
  }
}

/**
 * Log an error to console and optionally to Sentry.
 */
export function logError(error: unknown, context?: ErrorContext): void {
  const apiTelemetry = getSafeApiErrorTelemetry(error);
  const message = apiTelemetry
    ? apiTelemetry.errorClass
    : error instanceof Error
      ? error.message
      : String(error);
  const safeMessage = sanitizeDiagnosticText(
    message,
    "Error details available.",
  );
  const safeExtra = apiTelemetry
    ? apiTelemetry
    : context?.extra
      ? sanitizeDiagnosticMetadata(context.extra)
      : undefined;
  const source = sanitizeDiagnosticText(context?.source, "unknown");
  console.error(`[${source}]`, safeMessage, safeExtra ?? "");

  if (SENTRY_DSN) {
    void loadSentry().then((Sentry) => {
      const sentryError = new Error(safeMessage);
      sentryError.name = error instanceof Error ? error.name : "Error";

      Sentry.captureException(sentryError, {
        tags: { source },
        extra: safeExtra as Record<string, unknown> | undefined,
        level: context?.level ?? "error",
      });
    });
  }
}

/**
 * API failures use a deliberately closed telemetry envelope. In particular,
 * neither Error.message nor caller-provided extra metadata is forwarded,
 * because either can contain an RFC 9457 detail/body supplied by the backend.
 */
function getSafeApiErrorTelemetry(
  error: unknown,
): SafeApiErrorTelemetry | null {
  if (!(error instanceof Error) || error.name !== "APIError") {
    return null;
  }

  const telemetry = (error as Error & { telemetry?: unknown }).telemetry;
  if (typeof telemetry !== "object" || telemetry === null) return null;

  const candidate = telemetry as Record<string, unknown>;
  if (
    candidate.errorClass !== "APIError" ||
    typeof candidate.status !== "number" ||
    !Number.isInteger(candidate.status) ||
    candidate.status < 100 ||
    candidate.status > 599
  ) {
    return null;
  }

  const typeUri = canonicalProblemTypeUri(candidate.typeUri);
  const requestId =
    typeof candidate.requestId === "string" &&
    CORRELATION_ID_SHAPE.test(candidate.requestId)
      ? candidate.requestId
      : undefined;
  const correlationId =
    typeof candidate.correlationId === "string" &&
    CORRELATION_ID_SHAPE.test(candidate.correlationId)
      ? candidate.correlationId
      : undefined;

  return {
    status: candidate.status,
    errorClass: "APIError",
    ...(typeUri ? { typeUri } : {}),
    ...(requestId ? { requestId } : {}),
    ...(correlationId ? { correlationId } : {}),
  };
}
