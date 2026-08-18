import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  allowsMissingClerkProtectedRouteBypass,
  assertClerkConfiguredForProduction,
  hasValidClerkPublishableKey,
  hasValidClerkSecretKey,
  resolveClerkDomain,
  resolvePublicApiOrigin,
} from "@/lib/production-env";
import {
  DIGEST_UNSUBSCRIBE_COOKIE,
  hasUsableDigestUnsubscribeToken,
} from "@/lib/digest-unsubscribe";

// ---------------------------------------------------------------------------
// Per-request nonce generation
// ---------------------------------------------------------------------------

/**
 * Generate a cryptographically random base64url nonce for use in CSP.
 * The nonce is 128 bits (16 bytes), which is sufficient entropy per
 * the W3C CSP3 specification §2.6.1.
 */
function generateRandomBase64Url(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

function generateNonce(): string {
  return generateRandomBase64Url(16);
}

const isDev = process.env.NODE_ENV !== "production";
const clerkDomain = resolveClerkDomain(process.env.NEXT_PUBLIC_CLERK_DOMAIN);
const clerkScriptSources = clerkDomain
  ? [`https://${clerkDomain}`]
  : ["https://*.clerk.accounts.dev"];
const apiOrigin = resolvePublicApiOrigin({
  apiUrl: process.env.NEXT_PUBLIC_API_URL,
  nodeEnv: process.env.NODE_ENV,
  required:
    process.env.NODE_ENV === "production" &&
    process.env.NEXT_PUBLIC_DEMO_MODE !== "true",
});
const wsOrigin = apiOrigin ? apiOrigin.replace(/^http/u, "ws") : null;

/**
 * Build the per-request Content-Security-Policy header value.
 *
 * In production the nonce replaces 'unsafe-inline' in script-src, closing
 * the XSS vector that the static next.config.ts header leaves open.
 * The nonce is also forwarded as X-Nonce for response observability and CSP
 * contract verification.
 *
 * In development 'unsafe-eval' is retained for hot-reload. Production keeps
 * `wasm-unsafe-eval` for self-hosted chemistry WASM without allowing general
 * string-to-code evaluation on app, report, and share routes.
 */
function buildNoncedCSP(nonce: string): string {
  const scriptSrc = [
    "'self'",
    "'wasm-unsafe-eval'",
    `'nonce-${nonce}'`,
    ...clerkScriptSources,
    // Clerk uses Cloudflare Turnstile for bot protection
    "https://challenges.cloudflare.com",
    ...(isDev ? ["'unsafe-eval'", "https://unpkg.com"] : []),
  ];

  const connectSrc = [
    "'self'",
    "https://api.clerk.com",
    "https://*.clerk.accounts.dev",
    "https://*.accounts.dev",
    "https://clerk-telemetry.com",
    ...(apiOrigin ? [apiOrigin] : []),
    ...(wsOrigin ? [wsOrigin] : []),
    ...(isDev
      ? [
          "http://localhost:*",
          "http://127.0.0.1:*",
          "ws://localhost:*",
          "ws://127.0.0.1:*",
          "https://unpkg.com",
        ]
      : []),
  ];

  return [
    "default-src 'self'",
    `script-src ${scriptSrc.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' https://fonts.gstatic.com",
    `connect-src ${connectSrc.join(" ")}`,
    "frame-ancestors 'none'",
    // Clerk uses blob: workers; worker-src falls back to script-src without this
    "worker-src blob:",
    // Export previews use same-origin/blob iframes; Clerk uses Cloudflare Turnstile.
    "frame-src 'self' blob: https://challenges.cloudflare.com",
  ].join("; ");
}

const isAdminRoute = createRouteMatcher(["/admin(.*)"]);

const DEMO_ANALYSIS_ID = "ana_demo_001";
const LEGACY_DEMO_REPORT_ALIASES = new Set([
  "demo",
  "demo-analysis",
  "demo-analysis-001",
  "prv-2026-0142",
  "prv-demo-report",
  "sample",
  "rep_demo_001",
  "rpt_ana_demo_001",
  "rpt_demo_succinic_001",
]);

const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/share/(.*)",
  "/api/health",
  "/api/email/unsubscribe",
  "/unsubscribe/(.*)",
  "/opengraph-image",
  // Marketing pages — no auth required
  "/demo",
  "/demo/(.*)",
  "/sample-reports",
  "/sample-reports/(.*)",
  "/methodology",
  "/trust",
  "/compare/(.*)",
  "/for-biotech-founders",
  "/privacy",
  "/terms",
]);

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const clerkSecretKey = process.env.CLERK_SECRET_KEY;
const hasClerk =
  hasValidClerkPublishableKey(clerkKey) &&
  hasValidClerkSecretKey(clerkSecretKey);
const allowMissingClerkProtectedRouteBypass =
  allowsMissingClerkProtectedRouteBypass({
    nodeEnv: process.env.NODE_ENV,
    demoMode: process.env.NEXT_PUBLIC_DEMO_MODE,
    devAuthBypass: process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS,
  });
assertClerkConfiguredForProduction({
  nodeEnv: process.env.NODE_ENV,
  clerkPublishableKey: clerkKey,
  clerkSecretKey,
  requireSecret: true,
  runtimePhase: process.env.NEXT_PHASE,
});

// ---------------------------------------------------------------------------
// Middleware — per-request nonce injection + CSP enforcement
// ---------------------------------------------------------------------------
//
// The nonce-based CSP replaces the static 'unsafe-inline' set in next.config.ts.
// Each request gets a fresh nonce. The CSP is mirrored into the upstream request
// headers so Next.js can automatically nonce framework output. Product code does
// not own any inline bootstrap scripts; the light palette is server-rendered.
//
// Clerk's contentSecurityPolicy integration is promoted from report-only to
// enforcement mode now that product-owned inline bootstrap scripts are absent.

function applyNoncedCSP(
  response: NextResponse,
  nonce: string,
  csp: string,
): void {
  response.headers.set("Content-Security-Policy", csp);
  // Expose the nonce for response observability and automated CSP verification.
  response.headers.set("X-Nonce", nonce);
}

function nextResponseWithNonce(
  request: NextRequest,
  nonce: string,
): NextResponse {
  const csp = buildNoncedCSP(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  // Next's App Router reads the CSP request header to nonce its own inline
  // flight/bootstrap scripts, so mirror the enforced response CSP upstream.
  requestHeaders.set("content-security-policy", csp);
  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  applyNoncedCSP(response, nonce, csp);
  return response;
}

function redirectRetiredQuickAnalysis(
  request: NextRequest,
  nonce: string,
): NextResponse | null {
  const requestUrl = request.nextUrl ?? new URL(request.url);

  if (requestUrl.pathname !== "/analyses/quick") {
    return null;
  }

  const csp = buildNoncedCSP(nonce);
  const destination = new URL(request.url);
  destination.pathname = "/analyses/new";
  destination.searchParams.delete("preset");
  const response = NextResponse.redirect(destination);
  applyNoncedCSP(response, nonce, csp);
  return response;
}

function resolveLegacyReportAnalysisId(id: string): string {
  const decodedId = decodeURIComponent(id);
  const normalizedId = decodedId.toLowerCase();

  if (LEGACY_DEMO_REPORT_ALIASES.has(normalizedId)) {
    return DEMO_ANALYSIS_ID;
  }
  if (decodedId.startsWith("rpt_ana_")) {
    return decodedId.slice(4);
  }
  return decodedId;
}

function redirectLegacyReportRoute(
  request: NextRequest,
  nonce: string,
): NextResponse | null {
  const requestUrl = request.nextUrl ?? new URL(request.url);
  const [, segment, id, ...rest] = requestUrl.pathname.split("/");

  if (segment !== "reports" || !id || rest.length > 0) {
    return null;
  }

  const analysisId = resolveLegacyReportAnalysisId(id);
  // Only middleware-resolve references whose mapping is deterministic without
  // private data. Opaque report IDs must reach the authenticated page resolver,
  // which performs an org-scoped API lookup instead of treating them as an
  // analysis identity.
  if (analysisId === decodeURIComponent(id)) {
    return null;
  }
  const csp = buildNoncedCSP(nonce);
  const destination = new URL(request.url);
  destination.pathname = `/analyses/${encodeURIComponent(analysisId)}/report`;
  const response = NextResponse.redirect(destination);
  applyNoncedCSP(response, nonce, csp);
  return response;
}

function redirectDigestUnsubscribeTokenToCookie(
  request: NextRequest,
  nonce: string,
): NextResponse | null {
  const requestUrl = request.nextUrl ?? new URL(request.url);
  if (
    request.method !== "GET" ||
    requestUrl.pathname !== "/unsubscribe/digest" ||
    !requestUrl.searchParams.has("token")
  ) {
    return null;
  }

  const token = requestUrl.searchParams.get("token") ?? "";
  const destination = new URL(request.url);
  destination.searchParams.delete("token");
  const response = NextResponse.redirect(destination, 303);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set("X-Robots-Tag", "noindex, nofollow");
  if (hasUsableDigestUnsubscribeToken(token)) {
    response.cookies.set(DIGEST_UNSUBSCRIBE_COOKIE, token, {
      httpOnly: true,
      maxAge: 10 * 60,
      path: "/",
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
    });
  } else {
    response.cookies.delete(DIGEST_UNSUBSCRIBE_COOKIE);
  }
  applyNoncedCSP(response, nonce, buildNoncedCSP(nonce));
  return response;
}

const middleware = hasClerk
  ? clerkMiddleware(async (auth, request) => {
      const nonce = generateNonce();
      const digestUnsubscribeRedirect = redirectDigestUnsubscribeTokenToCookie(
        request,
        nonce,
      );
      if (digestUnsubscribeRedirect) {
        return digestUnsubscribeRedirect;
      }
      const retiredQuickRedirect = redirectRetiredQuickAnalysis(request, nonce);
      if (retiredQuickRedirect) {
        return retiredQuickRedirect;
      }
      const legacyReportRedirect = redirectLegacyReportRoute(request, nonce);
      if (legacyReportRedirect) {
        return legacyReportRedirect;
      }

      if (isAdminRoute(request)) {
        // Admin routes require both authentication and the org:admin role.
        await auth.protect(
          (has) => has({ role: "org:admin" }) || has({ role: "admin" }),
        );
      } else if (!isPublicRoute(request)) {
        await auth.protect();
      }
      return nextResponseWithNonce(request, nonce);
    })
  : (request: NextRequest) => {
      const nonce = generateNonce();
      const digestUnsubscribeRedirect = redirectDigestUnsubscribeTokenToCookie(
        request,
        nonce,
      );
      if (digestUnsubscribeRedirect) {
        return digestUnsubscribeRedirect;
      }
      const retiredQuickRedirect = redirectRetiredQuickAnalysis(request, nonce);
      if (retiredQuickRedirect) {
        return retiredQuickRedirect;
      }
      const legacyReportRedirect = redirectLegacyReportRoute(request, nonce);
      if (legacyReportRedirect) {
        return legacyReportRedirect;
      }

      if (isPublicRoute(request)) {
        return nextResponseWithNonce(request, nonce);
      }
      if (allowMissingClerkProtectedRouteBypass) {
        return nextResponseWithNonce(request, nonce);
      }
      return new NextResponse("Authentication middleware is not configured.", {
        status: 503,
      });
    };

export default middleware;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|avif|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|txt|wasm)).*)",
    "/(api|trpc)(.*)",
  ],
};
