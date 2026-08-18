import { afterEach, describe, expect, it, vi } from "vitest";

async function loadCspForEnv(nodeEnv: "development" | "production") {
  vi.resetModules();
  vi.stubEnv("NODE_ENV", nodeEnv);
  vi.stubEnv(
    "NEXT_PUBLIC_API_URL",
    nodeEnv === "production"
      ? "https://api.praviar.example"
      : "http://localhost:8000",
  );
  vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
  vi.stubEnv("NEXT_PUBLIC_CLERK_DOMAIN", undefined);
  const config = (await import("../../next.config")).default;
  const headers = await config.headers?.();
  const csp = headers?.[0]?.headers.find(
    (header) => header.key === "Content-Security-Policy",
  )?.value;

  if (!csp) {
    throw new Error("Content-Security-Policy header was not configured");
  }

  return csp;
}

describe("next.config CSP fallback", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("does not allow general unsafe eval in production", async () => {
    const csp = await loadCspForEnv("production");
    const scriptSrc = csp
      .split("; ")
      .find((directive) => directive.startsWith("script-src "));
    const connectSrc = csp
      .split("; ")
      .find((directive) => directive.startsWith("connect-src "));

    expect(csp).toContain("'wasm-unsafe-eval'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(connectSrc).not.toMatch(/(?:^|\s)wss:(?:\s|$)/u);
  });

  it("keeps unsafe eval scoped to development tooling", async () => {
    const csp = await loadCspForEnv("development");

    expect(csp).toContain("'unsafe-eval'");
  });

  it("allows same-origin and blob report previews without broad frame access", async () => {
    const csp = await loadCspForEnv("production");

    expect(csp).toContain(
      "frame-src 'self' blob: https://challenges.cloudflare.com",
    );
    expect(csp).not.toContain("frame-src *");
  });

  it("uses an isolated Playwright dist directory only when requested", async () => {
    vi.resetModules();
    vi.stubEnv("PLAYWRIGHT_NEXT_DIST_DIR", ".next/matrix-520");

    const isolatedConfig = (await import("../../next.config")).default;

    expect(isolatedConfig.distDir).toBe(".next/matrix-520");

    vi.resetModules();
    vi.unstubAllEnvs();

    const defaultConfig = (await import("../../next.config")).default;

    expect(defaultConfig.distDir).toBe(".next");
  });

  it("interpolates only canonical validated API and Clerk origins", async () => {
    vi.resetModules();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://API.Praviar.Example:443/");
    vi.stubEnv(
      "NEXT_PUBLIC_CLERK_DOMAIN",
      "Tenant.Clerk.Accounts.Dev",
    );

    const config = (await import("../../next.config")).default;
    const headers = await config.headers?.();
    const csp = headers?.[0]?.headers.find(
      (header) => header.key === "Content-Security-Policy",
    )?.value;

    expect(csp).toContain("https://api.praviar.example");
    expect(csp).toContain("wss://api.praviar.example");
    expect(csp).toContain("https://tenant.clerk.accounts.dev");
    expect(csp).not.toContain("API.Praviar.Example");
    expect(csp).not.toContain("Tenant.Clerk.Accounts.Dev");
  });

  it("rejects unsafe values before CSP construction", async () => {
    vi.resetModules();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.praviar.example/v1");
    vi.stubEnv("NEXT_PUBLIC_CLERK_DOMAIN", undefined);

    await expect(import("../../next.config")).rejects.toThrow(
      "NEXT_PUBLIC_API_URL",
    );

    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.praviar.example");
    vi.stubEnv(
      "NEXT_PUBLIC_CLERK_DOMAIN",
      "tenant.clerk.accounts.dev; script-src 'unsafe-inline'",
    );

    await expect(import("../../next.config")).rejects.toThrow(
      "NEXT_PUBLIC_CLERK_DOMAIN",
    );
  });
});
