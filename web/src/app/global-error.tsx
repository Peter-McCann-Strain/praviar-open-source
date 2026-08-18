"use client";

import Link from "next/link";

import { PraviarMark } from "@/components/icons/praviar-mark";

/**
 * Global error boundary for layout-level errors.
 *
 * This catches errors in the root layout itself (e.g. ClerkProvider, Providers, etc.).
 * Unlike error.tsx, global-error must render its own <html> and <body> tags because
 * the root layout is broken.
 *
 * Logs a non-sensitive support reference while keeping the broken-layout
 * fallback safe to show.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const safeDigest = formatSupportReference(error.digest);

  // Log immediately — the normal provider-based logger may be unavailable.
  // Never include message/stack here because they can contain private inputs,
  // tokens, URLs, or provider diagnostics.
  if (typeof console !== "undefined") {
    console.error("[GlobalErrorBoundary] Layout render failed", {
      digest: safeDigest,
      errorName: error.name,
    });
  }

  return (
    <html lang="en" className="light">
      <body
        style={{
          margin: 0,
          padding: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--bg-base, #F6F4EF)",
          color: "var(--text-primary, #0B1F24)",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <main
          id="main-content"
          style={{
            maxWidth: 480,
            textAlign: "center",
            padding: 32,
          }}
        >
          <div
            style={{
              width: 72,
              height: 72,
              margin: "0 auto 24px",
              borderRadius: 8,
              backgroundColor:
                "color-mix(in srgb, var(--brand-secondary, #B87333) 12%, transparent)",
              border:
                "1px solid color-mix(in srgb, var(--brand-secondary, #B87333) 28%, transparent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <PraviarMark size={48} variant="onLight" aria-hidden="true" />
          </div>

          <p
            style={{
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--text-tertiary, #516F68)",
              marginBottom: 12,
            }}
          >
            Praviar
          </p>

          <h1
            style={{
              fontSize: 20,
              fontWeight: 600,
              marginBottom: 8,
            }}
          >
            Critical Application Error
          </h1>

          <p
            style={{
              fontSize: 14,
              color: "var(--text-secondary, #0E6F68)",
              marginBottom: 16,
            }}
          >
            The application layout encountered a fatal error and could not
            render.
          </p>

          <p
            style={{
              fontSize: 12,
              lineHeight: 1.6,
              color: "var(--text-tertiary, #516F68)",
              backgroundColor: "var(--surface-muted, #F2F6F4)",
              border:
                "1px solid color-mix(in srgb, var(--brand-primary, #0E6F68) 16%, transparent)",
              borderRadius: 8,
              padding: "12px 16px",
              textAlign: "center",
              marginBottom: 8,
            }}
          >
            Diagnostic context has been logged. Retry to request a fresh shell.
          </p>

          {safeDigest && (
            <p
              style={{
                fontSize: 11,
                fontFamily: "monospace",
                color: "var(--text-tertiary, #516F68)",
                marginBottom: 24,
                overflowWrap: "anywhere",
              }}
            >
              Reference: {safeDigest}
            </p>
          )}

          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              onClick={reset}
              style={{
                padding: "10px 20px",
                minHeight: 44,
                borderRadius: 8,
                border: "none",
                backgroundColor: "var(--brand-primary, #0E6F68)",
                color: "var(--brand-paper, #F6F4EF)",
                fontSize: 14,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Try Again
            </button>
            <Link
              href="/"
              style={{
                boxSizing: "border-box",
                display: "inline-flex",
                alignItems: "center",
                padding: "10px 20px",
                minHeight: 44,
                borderRadius: 8,
                border: "1px solid var(--brand-mint, #5FB7A6)",
                backgroundColor: "transparent",
                color: "var(--brand-primary, #0E6F68)",
                fontSize: 14,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Go Home
            </Link>
          </div>
        </main>
      </body>
    </html>
  );
}

function formatSupportReference(detail?: string | null): string | null {
  if (!detail) {
    return null;
  }

  const reference = detail
    .replace(/^(?:reference|ref)\s*:\s*/iu, "")
    .replace(/\s+/gu, " ")
    .trim();

  if (!reference) {
    return null;
  }

  const opaqueReferencePattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,95}$/u;

  return opaqueReferencePattern.test(reference) ? reference : null;
}
