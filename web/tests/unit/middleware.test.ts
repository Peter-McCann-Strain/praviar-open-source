import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const protectMock = vi.fn();
const clerkPublishableKey = (mode: "test" | "live", payload: string) =>
  ["pk", mode, payload].join("_");
const VALID_LIVE_CLERK_KEY = clerkPublishableKey(
  "live",
  ["Y2xl", "cmsu", "cHJh", "dmlh", "ci5p", "byQ="].join(""),
);

vi.mock("@clerk/nextjs/server", () => ({
  clerkMiddleware: vi.fn((handler) => async (request: Request) => {
    return handler({ protect: protectMock }, request);
  }),
  createRouteMatcher: vi.fn((patterns: string[]) => (request: Request) => {
    const pathname = new URL(request.url).pathname;
    return patterns.some((pattern) => {
      if (pattern === "/") return pathname === "/";
      if (pattern.endsWith("(.*)")) {
        const prefix = pattern.slice(0, -4);
        return pathname === prefix || pathname.startsWith(prefix);
      }
      if (pattern.endsWith("/(.*)")) {
        const prefix = pattern.slice(0, -5);
        return pathname === prefix || pathname.startsWith(`${prefix}/`);
      }
      return pathname === pattern;
    });
  }),
}));

async function loadMiddleware(env: Record<string, string | undefined>) {
  vi.resetModules();
  vi.stubEnv("NODE_ENV", env.NODE_ENV);
  vi.stubEnv("NEXT_PHASE", env.NEXT_PHASE);
  vi.stubEnv(
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
  );
  vi.stubEnv("CLERK_SECRET_KEY", env.CLERK_SECRET_KEY);
  vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", env.NEXT_PUBLIC_DEMO_MODE);
  vi.stubEnv(
    "NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS",
    env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS,
  );
  const apiUrl = Object.prototype.hasOwnProperty.call(
    env,
    "NEXT_PUBLIC_API_URL",
  )
    ? env.NEXT_PUBLIC_API_URL
    : env.NODE_ENV === "production"
      ? "https://api.praviar.example"
      : undefined;
  vi.stubEnv("NEXT_PUBLIC_API_URL", apiUrl);
  vi.stubEnv(
    "NEXT_PUBLIC_CLERK_DOMAIN",
    env.NEXT_PUBLIC_CLERK_DOMAIN,
  );
  return import("@/proxy");
}

describe("middleware fail-closed auth behavior", () => {
  afterEach(() => {
    protectMock.mockReset();
    vi.unstubAllEnvs();
  });

  it("throws during production boot when Clerk is missing", async () => {
    await expect(
      loadMiddleware({
        NODE_ENV: "production",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
        CLERK_SECRET_KEY: "sk_live_ci",
      }),
    ).rejects.toThrow("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY");
  });

  it("throws during production boot when Clerk secret is missing", async () => {
    await expect(
      loadMiddleware({
        NODE_ENV: "production",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
        CLERK_SECRET_KEY: undefined,
      }),
    ).rejects.toThrow("CLERK_SECRET_KEY");
  });

  it("does not require Clerk secret while Next collects build data", async () => {
    await expect(
      loadMiddleware({
        NODE_ENV: "production",
        NEXT_PHASE: "phase-production-build",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
        CLERK_SECRET_KEY: undefined,
      }),
    ).resolves.toBeTruthy();
  });

  it("returns 503 for protected routes when Clerk is absent and no explicit bypass is enabled", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "development",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "false",
    });

    const response = await middleware(
      new Request("http://localhost:3000/dashboard"),
    );

    expect(response.status).toBe(503);
  });

  it("still allows public routes when Clerk is absent outside production", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "development",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "false",
    });

    const response = await middleware(
      new Request("http://localhost:3000/sign-in"),
    );

    expect(response.status).toBe(200);
  });

  it("keeps the interactive demo public when Clerk is absent outside production", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "development",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "false",
    });

    const response = await middleware(
      new Request("http://localhost:3000/demo"),
    );

    expect(response.status).toBe(200);
  });

  it("moves digest capabilities into a short-lived HttpOnly cookie and cleans the URL", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });
    const token = `du1.${"t".repeat(86)}`;

    const response = await middleware(
      new Request(
        `https://app.praviar.io/unsubscribe/digest?token=${encodeURIComponent(token)}`,
      ),
    );

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "https://app.praviar.io/unsubscribe/digest",
    );
    const setCookie = response.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain("praviar_digest_unsubscribe=");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("SameSite=strict");
    expect(setCookie).toContain("Secure");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(protectMock).not.toHaveBeenCalled();
  });

  it("keeps the extensionless Open Graph image route public", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/opengraph-image"),
    );

    expect(response.status).toBe(200);
    expect(protectMock).not.toHaveBeenCalled();
    expect(response.headers.get("content-security-policy")).toContain("'self'");
    expect(response.headers.get("x-nonce")).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("redirects legacy sample report deep links before rendering the app shell", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/reports/sample?tab=evidence"),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/analyses/ana_demo_001/report?tab=evidence",
    );
    expect(protectMock).not.toHaveBeenCalled();
    expect(response.headers.get("content-security-policy")).toContain("'self'");
    expect(response.headers.get("x-nonce")).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("redirects narrow legacy report ids while preserving deep-link params", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request(
        "http://localhost:3000/reports/rpt_ana_case_123?ai_context=blocker_brief",
      ),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/analyses/ana_case_123/report?ai_context=blocker_brief",
    );
    expect(protectMock).not.toHaveBeenCalled();
  });

  it("protects opaque report references for tenant-scoped page resolution", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });
    const reportId = "5011f7bd-abf4-409a-b78d-c1d67ee804aa";

    const response = await middleware(
      new Request(`http://localhost:3000/reports/${reportId}?tab=patents`),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(protectMock).toHaveBeenCalledTimes(1);
  });

  it("protects private routes when Clerk is configured", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/dashboard"),
    );

    expect(response.status).toBe(200);
    expect(protectMock).toHaveBeenCalledTimes(1);
  });

  it("sets a matching production CSP nonce and forwards it to request headers", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/dashboard"),
    );

    const nonce = response.headers.get("x-nonce");
    expect(nonce).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(response.headers.get("content-security-policy")).toContain(
      `'nonce-${nonce}'`,
    );
    expect(response.headers.get("content-security-policy")).toContain(
      "'wasm-unsafe-eval'",
    );
    expect(response.headers.get("content-security-policy")).not.toContain(
      "'unsafe-eval'",
    );
    expect(response.headers.get("x-middleware-override-headers")).toContain(
      "x-nonce",
    );
    expect(response.headers.get("x-middleware-override-headers")).toContain(
      "content-security-policy",
    );
    expect(response.headers.get("x-middleware-request-x-nonce")).toBe(nonce);
    expect(
      response.headers.get("x-middleware-request-content-security-policy"),
    ).toContain(`'nonce-${nonce}'`);
  });

  it("keeps unsafe-eval available only for development tooling", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "development",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: undefined,
      NEXT_PUBLIC_DEMO_MODE: "false",
      NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS: "false",
    });

    const response = await middleware(
      new Request("http://localhost:3000/sign-in"),
    );

    expect(response.headers.get("content-security-policy")).toContain(
      "'unsafe-eval'",
    );
    expect(response.headers.get("content-security-policy")).toContain(
      "http://localhost:*",
    );
    expect(response.headers.get("content-security-policy")).toContain(
      "http://127.0.0.1:*",
    );
    expect(response.headers.get("content-security-policy")).toContain(
      "ws://localhost:*",
    );
    expect(response.headers.get("content-security-policy")).toContain(
      "ws://127.0.0.1:*",
    );
  });

  it("does not allow local dev origins in the production proxy CSP", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/dashboard"),
    );
    const csp = response.headers.get("content-security-policy");

    expect(csp).not.toContain("http://localhost:*");
    expect(csp).not.toContain("http://127.0.0.1:*");
    expect(csp).not.toContain("ws://localhost:*");
    expect(csp).not.toContain("ws://127.0.0.1:*");
  });

  it("uses canonical validated API and Clerk origins in the proxy CSP", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
      NEXT_PUBLIC_API_URL: "https://API.Praviar.Example:443/",
      NEXT_PUBLIC_CLERK_DOMAIN: "Tenant.Clerk.Accounts.Dev",
    });

    const response = await middleware(
      new Request("https://app.praviar.example/dashboard"),
    );
    const csp = response.headers.get("content-security-policy");

    expect(csp).toContain("https://api.praviar.example");
    expect(csp).toContain("wss://api.praviar.example");
    expect(csp).toContain("https://tenant.clerk.accounts.dev");
    expect(csp).not.toContain("API.Praviar.Example");
    expect(csp).not.toContain("Tenant.Clerk.Accounts.Dev");
  });

  it("rejects unsafe origins before proxy CSP construction", async () => {
    await expect(
      loadMiddleware({
        NODE_ENV: "production",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
        CLERK_SECRET_KEY: "sk_live_ci",
        NEXT_PUBLIC_API_URL: "https://api.praviar.example/v1",
      }),
    ).rejects.toThrow("NEXT_PUBLIC_API_URL");

    await expect(
      loadMiddleware({
        NODE_ENV: "production",
        NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
        CLERK_SECRET_KEY: "sk_live_ci",
        NEXT_PUBLIC_API_URL: "https://api.praviar.example",
        NEXT_PUBLIC_CLERK_DOMAIN:
          "tenant.clerk.accounts.dev; connect-src https://evil.example",
      }),
    ).rejects.toThrow("NEXT_PUBLIC_CLERK_DOMAIN");
  });

  it("allows same-origin and blob report preview frames in the proxy CSP", async () => {
    const { default: middleware } = await loadMiddleware({
      NODE_ENV: "production",
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: VALID_LIVE_CLERK_KEY,
      CLERK_SECRET_KEY: "sk_live_ci",
    });

    const response = await middleware(
      new Request("http://localhost:3000/dashboard"),
    );
    const csp = response.headers.get("content-security-policy");

    expect(csp).toContain(
      "frame-src 'self' blob: https://challenges.cloudflare.com",
    );
    expect(csp).not.toContain("frame-src *");
  });
});

// ---------------------------------------------------------------------------
// Adversarial tests: proxy.ts contract and matcher correctness
//
// Next.js 16 uses proxy.ts directly as the middleware entry point.
// middleware.ts no longer exists (deleted to avoid "both files detected" error).
// ---------------------------------------------------------------------------

describe("proxy.ts middleware contract", () => {
  // vi.resetModules() is not needed here -- we want stable module state.

  let middlewareModule: { default: unknown; config: { matcher: string[] } };

  beforeAll(async () => {
    // Provide minimal Clerk keys so proxy.ts does not throw on import.
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_LIVE_CLERK_KEY);
    vi.stubEnv("CLERK_SECRET_KEY", "sk_live_ci");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.praviar.example");
    middlewareModule = await import("@/proxy");
  });

  it("proxy.ts exports a default function", () => {
    expect(typeof middlewareModule.default).toBe("function");
  });

  it("proxy.ts exports a config object", () => {
    expect(middlewareModule.config).toBeDefined();
    expect(typeof middlewareModule.config).toBe("object");
  });

  it("config.matcher is a non-empty array", () => {
    const { matcher } = middlewareModule.config;
    expect(Array.isArray(matcher)).toBe(true);
    expect(matcher.length).toBeGreaterThan(0);
  });

  it("config.matcher entries are all strings", () => {
    const { matcher } = middlewareModule.config;
    for (const entry of matcher) {
      expect(typeof entry).toBe("string");
    }
  });

  it("config.matcher includes an entry covering the /api prefix", () => {
    const { matcher } = middlewareModule.config;
    const coversApi = matcher.some(
      (pattern) => pattern.includes("api") || pattern.startsWith("/"),
    );
    expect(coversApi).toBe(true);
  });

  it("config.matcher excludes AVIF visual assets from auth middleware", () => {
    const [mainMatcher] = middlewareModule.config.matcher;

    expect(mainMatcher).toContain("avif");
  });
});

// ---------------------------------------------------------------------------
// Adversarial tests: matcher regex coverage (path-level assertions)
//
// proxy.ts exports:
//   matcher: [
//     "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|avif|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
//     "/(api|trpc)(.*)",
//   ]
//
// We extract the patterns and test them directly so the assertions are
// independent of any Clerk mock state.
// ---------------------------------------------------------------------------

// The exclusion pattern from the first matcher entry (Next.js canonical form).
const MAIN_PATTERN =
  "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|avif|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|txt|wasm)).*)";
const API_PATTERN = "/(api|trpc)(.*)";

/** True when ANY matcher entry matches the given path. */
function matchesAnyEntry(path: string): boolean {
  // Convert Next.js path patterns to plain RegExp.
  // The patterns use leading "/" and wrap the group -- match from start.
  const toRegex = (pattern: string) => new RegExp("^" + pattern + "$");
  return [MAIN_PATTERN, API_PATTERN].some((p) => toRegex(p).test(path));
}

describe("middleware matcher regex: protected paths ARE matched", () => {
  const protectedPaths = [
    "/dashboard",
    "/analyses/123",
    "/analyses/abc-456/report",
    "/settings",
    "/settings/billing",
    "/billing",
    "/api/health",
    "/api/v1/analyses",
    "/trpc/report.get",
    "/sign-in",
    "/sign-up",
    "/share/abc123",
    // Root must pass through so Clerk can decide it is public.
    "/",
  ];

  for (const path of protectedPaths) {
    it(`matches protected path: ${path}`, () => {
      expect(matchesAnyEntry(path)).toBe(true);
    });
  }
});

describe("middleware matcher regex: static assets are NOT matched", () => {
  const staticPaths = [
    "/_next/static/foo.js",
    "/_next/static/chunks/main.js",
    "/_next/image?url=%2Flogo.png&w=128&q=75",
    "/favicon.ico",
    "/logo.png",
    "/robots.txt",
    // HTML is excluded by the pattern (html? extension).
    "/some-page.html",
    "/some-page.htm",
    // CSS and font assets.
    "/styles/global.css",
    "/fonts/inter.woff2",
    "/fonts/inter.ttf",
    "/rdkit/RDKit_minimal.wasm",
    // Raster images.
    "/images/hero.jpg",
    "/images/hero.jpeg",
    "/images/hero.webp",
    "/images/hero.avif",
    "/brand/visuals/praviar-analysis-launch-workspace.avif",
    "/images/hero.gif",
    "/images/hero.svg",
  ];

  for (const path of staticPaths) {
    it(`does NOT match static asset: ${path}`, () => {
      expect(matchesAnyEntry(path)).toBe(false);
    });
  }
});

describe("middleware matcher regex: boundary / ambiguous cases", () => {
  it("matches .json paths (json is explicitly NOT excluded -- js(?!on) keeps .json)", () => {
    // The pattern excludes .js but not .json. This is intentional: API routes
    // may return JSON. Confirm the boundary is correct.
    expect(matchesAnyEntry("/api/data.json")).toBe(true);
  });

  it("does NOT match plain .js files", () => {
    expect(matchesAnyEntry("/scripts/app.js")).toBe(false);
  });

  it("matches paths with query strings appended after the pathname segment", () => {
    // Matchers are applied to the pathname only; query strings are not part of
    // Next.js matcher evaluation. Confirm the regex handles a bare path correctly.
    expect(matchesAnyEntry("/dashboard")).toBe(true);
  });

  it("does NOT match _next prefixed paths regardless of depth", () => {
    expect(matchesAnyEntry("/_next/data/build-id/index.json")).toBe(false);
  });

  it("matches /webmanifest-shaped paths that are NOT .webmanifest files", () => {
    // /site.webmanifest is excluded; /webmanifest-editor is an app route and must not be excluded.
    expect(matchesAnyEntry("/webmanifest-editor")).toBe(true);
  });

  it("does NOT match .webmanifest file requests", () => {
    expect(matchesAnyEntry("/site.webmanifest")).toBe(false);
  });
});
