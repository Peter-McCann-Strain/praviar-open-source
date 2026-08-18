import type { NextConfig } from "next";
import bundleAnalyzer from "@next/bundle-analyzer";
import {
  resolveClerkDomain,
  resolvePublicApiOrigin,
} from "./src/lib/production-env";

const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

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

/**
 * Build the Content-Security-Policy header.
 *
 * Development: Permissive — includes unsafe-eval for hot-reload, localhost for connect-src.
 * Production:  Strict — no unsafe-eval (wasm-unsafe-eval only for RDKit WASM), no localhost.
 *
 * Matched app routes receive a stricter per-request nonce policy from proxy.ts.
 * This fallback still refuses product-owned inline scripts and broad websocket
 * access so unmatched responses cannot silently weaken the production posture.
 */
function buildCSP(): string {
  const scriptSrc = [
    "'self'",
    "'wasm-unsafe-eval'",
    ...clerkScriptSources,
    // Clerk uses Cloudflare Turnstile for bot protection
    "https://challenges.cloudflare.com",
  ];

  if (isDev) {
    scriptSrc.push("'unsafe-eval'");
    // unpkg is restricted to dev only — it is a third-party CDN and any package
    // hosted there could be used to exfiltrate data (high-severity XSS vector).
    scriptSrc.push("https://unpkg.com");
  }

  const connectSrc = [
    "'self'",
    "https://api.clerk.com",
    "https://*.clerk.accounts.dev",
    "https://*.accounts.dev",
    "https://clerk-telemetry.com",
  ];
  if (apiOrigin) {
    connectSrc.push(apiOrigin);
    connectSrc.push(apiOrigin.replace(/^http/u, "ws"));
  }

  if (isDev) {
    connectSrc.push("http://localhost:*");
    connectSrc.push("http://127.0.0.1:*");
    connectSrc.push("ws://localhost:*");
    connectSrc.push("ws://127.0.0.1:*");
  }

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

const nextConfig: NextConfig = {
  agentRules: false,
  distDir: process.env.PLAYWRIGHT_NEXT_DIST_DIR ?? ".next",
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  reactCompiler: true,
  devIndicators: false,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "Content-Security-Policy",
            value: buildCSP(),
          },
        ],
      },
      {
        source: "/unsubscribe/digest",
        headers: [
          { key: "Cache-Control", value: "no-store" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
        ],
      },
    ];
  },
};

export default withBundleAnalyzer(nextConfig);
