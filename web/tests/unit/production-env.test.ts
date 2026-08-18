import { describe, expect, it } from "vitest";

import {
  allowsMissingClerkProtectedRouteBypass,
  assertAppUrlConfiguredForProduction,
  assertClerkConfiguredForProduction,
  hasValidClerkPublishableKey,
  hasValidClerkSecretKey,
  resolveAppUrl,
  resolveClerkDomain,
  resolvePublicApiOrigin,
} from "@/lib/production-env";

const clerkPublishableKey = (mode: "test" | "live", payload: string) =>
  ["pk", mode, payload].join("_");
const VALID_TEST_CLERK_KEY = clerkPublishableKey(
  "test",
  [
    "Zm9v",
    "LWJh",
    "ci0x",
    "My5j",
    "bGVy",
    "ay5h",
    "Y2Nv",
    "dW50",
    "cy5k",
    "ZXYk",
  ].join(""),
);
const VALID_LIVE_CLERK_KEY = clerkPublishableKey(
  "live",
  ["Y2xl", "cmsu", "cHJh", "dmlh", "ci5p", "byQ="].join(""),
);

describe("production env validation", () => {
  it("accepts valid Clerk publishable keys", () => {
    expect(hasValidClerkPublishableKey(VALID_TEST_CLERK_KEY)).toBe(true);
    expect(hasValidClerkPublishableKey(VALID_LIVE_CLERK_KEY)).toBe(true);
    expect(hasValidClerkPublishableKey("sk_live_abc")).toBe(false);
    expect(hasValidClerkPublishableKey("pk_test_abc")).toBe(false);
    expect(hasValidClerkPublishableKey("pk_live_not-base64")).toBe(false);
    expect(hasValidClerkPublishableKey(`${VALID_LIVE_CLERK_KEY}extra`)).toBe(
      false,
    );
    expect(hasValidClerkPublishableKey(undefined)).toBe(false);
  });

  it("accepts valid Clerk secret keys", () => {
    expect(hasValidClerkSecretKey("sk_test_abc")).toBe(true);
    expect(hasValidClerkSecretKey("sk_live_abc")).toBe(true);
    expect(hasValidClerkSecretKey("pk_live_abc")).toBe(false);
    expect(hasValidClerkSecretKey(undefined)).toBe(false);
  });

  it("fails closed when Clerk is missing in production", () => {
    expect(() =>
      assertClerkConfiguredForProduction({
        nodeEnv: "production",
        clerkPublishableKey: undefined,
        clerkSecretKey: "sk_live_abc",
      }),
    ).toThrow("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY");

    expect(() =>
      assertClerkConfiguredForProduction({
        nodeEnv: "production",
        clerkPublishableKey: VALID_LIVE_CLERK_KEY,
        clerkSecretKey: undefined,
        requireSecret: true,
      }),
    ).toThrow("CLERK_SECRET_KEY");
  });

  it("does not require server-only Clerk secrets during the production build phase", () => {
    expect(() =>
      assertClerkConfiguredForProduction({
        nodeEnv: "production",
        clerkPublishableKey: VALID_LIVE_CLERK_KEY,
        clerkSecretKey: undefined,
        requireSecret: true,
        runtimePhase: "phase-production-build",
      }),
    ).not.toThrow();
  });

  it("allows missing Clerk only outside production", () => {
    expect(() =>
      assertClerkConfiguredForProduction({
        nodeEnv: "development",
        clerkPublishableKey: undefined,
        clerkSecretKey: undefined,
      }),
    ).not.toThrow();
  });

  it("allows missing Clerk protected-route bypass only when explicitly enabled outside production", () => {
    expect(
      allowsMissingClerkProtectedRouteBypass({
        nodeEnv: "development",
        devAuthBypass: "true",
      }),
    ).toBe(true);
    expect(
      allowsMissingClerkProtectedRouteBypass({
        nodeEnv: "development",
        demoMode: "true",
      }),
    ).toBe(true);
    expect(
      allowsMissingClerkProtectedRouteBypass({
        nodeEnv: "development",
      }),
    ).toBe(false);
    expect(
      allowsMissingClerkProtectedRouteBypass({
        nodeEnv: "production",
        devAuthBypass: "true",
        demoMode: "true",
      }),
    ).toBe(false);
  });

  it("rejects missing or local app URLs in production", () => {
    expect(() =>
      assertAppUrlConfiguredForProduction({
        nodeEnv: "production",
        appUrl: undefined,
      }),
    ).toThrow("NEXT_PUBLIC_APP_URL is required");

    for (const appUrl of [
      "http://localhost:3000",
      "https://preview.localhost",
      "http://127.0.0.1:3000",
      "http://[::1]:3000",
      "http://0.0.0.0:3000",
    ]) {
      expect(() =>
        assertAppUrlConfiguredForProduction({
          nodeEnv: "production",
          appUrl,
        }),
      ).toThrow("local hosts");
    }
  });

  it("accepts production app URLs", () => {
    expect(() =>
      assertAppUrlConfiguredForProduction({
        nodeEnv: "production",
        appUrl: "https://app.praviar.io",
      }),
    ).not.toThrow();
  });

  it("requires an origin-only HTTPS canonical URL in production", () => {
    for (const appUrl of [
      "not-a-url",
      "http://app.praviar.example",
      "https://user:password@app.praviar.example",
      "https://app.praviar.example/path",
      "https://app.praviar.example?preview=true",
      "https://app.praviar.example#preview",
    ]) {
      expect(() =>
        assertAppUrlConfiguredForProduction({
          nodeEnv: "production",
          appUrl,
        }),
      ).toThrow();
    }
  });

  it("uses localhost only outside production and normalizes configured origins", () => {
    expect(resolveAppUrl({ nodeEnv: "test" })).toBe("http://localhost:3000");
    expect(
      resolveAppUrl({
        nodeEnv: "production",
        appUrl: "https://app.praviar.example/",
      }),
    ).toBe("https://app.praviar.example");
  });

  it("canonicalizes validated API origins before runtime use", () => {
    expect(
      resolvePublicApiOrigin({
        nodeEnv: "production",
        apiUrl: "https://API.Praviar.Example:443/",
        required: true,
      }),
    ).toBe("https://api.praviar.example");
    expect(
      resolvePublicApiOrigin({
        nodeEnv: "development",
        apiUrl: "http://localhost:8000/",
      }),
    ).toBe("http://localhost:8000");
    expect(
      resolvePublicApiOrigin({
        nodeEnv: "development",
        apiUrl: "https://8.8.8.8/",
      }),
    ).toBe("https://8.8.8.8");
    expect(
      resolvePublicApiOrigin({
        nodeEnv: "development",
        apiUrl: "http://[::1]:8000/",
      }),
    ).toBe("http://[::1]:8000");
    expect(
      resolvePublicApiOrigin({ nodeEnv: "development", apiUrl: undefined }),
    ).toBeNull();
  });

  it("requires a remote origin-only HTTPS API URL in production", () => {
    expect(() =>
      resolvePublicApiOrigin({
        nodeEnv: "production",
        apiUrl: undefined,
        required: true,
      }),
    ).toThrow("NEXT_PUBLIC_API_URL is required");

    for (const apiUrl of [
      "not-a-url",
      "http://api.praviar.example",
      "https://user:password@api.praviar.example",
      "https://api.praviar.example/v1",
      "https://api.praviar.example?tenant=one",
      "https://api.praviar.example#fragment",
      "https://api.praviar.example.",
      "https://localhost:8000",
      "https://127.0.0.1:8000",
      "https://10.2.3.4",
      "https://172.20.0.4",
      "https://192.168.1.8",
      "https://8.8.8.8",
      "https://203.0.113.10",
      "https://198.18.0.1",
      "https://224.0.0.1",
      "https://240.0.0.1",
      "https://[::1]:8000",
      "https://[fd00::1]",
      "https://[fe90::1]",
      "https://[fea0::1]",
      "https://[febf::1]",
      "https://[fec0::1]",
      "https://[ff02::1]",
      "https://[2606:4700:4700::1111]",
      "https://[::ffff:127.0.0.1]",
      "https://[::ffff:10.0.0.1]",
      "javascript:alert(1)",
    ]) {
      expect(() =>
        resolvePublicApiOrigin({
          nodeEnv: "production",
          apiUrl,
          required: true,
        }),
      ).toThrow();
    }
  });

  it("accepts normal remote HTTPS DNS API origins in production", () => {
    expect(
      resolvePublicApiOrigin({
        nodeEnv: "production",
        apiUrl: "https://API.Praviar.IO:443/",
        required: true,
      }),
    ).toBe("https://api.praviar.io");
  });

  it("canonicalizes a valid Clerk custom domain", () => {
    expect(resolveClerkDomain("Tenant.Clerk.Accounts.Dev")).toBe(
      "tenant.clerk.accounts.dev",
    );
    expect(resolveClerkDomain(undefined)).toBeNull();
  });

  it("rejects Clerk inputs that could alter a CSP directive", () => {
    for (const clerkDomain of [
      "https://tenant.clerk.accounts.dev",
      "tenant.clerk.accounts.dev/path",
      "tenant.clerk.accounts.dev?next=evil",
      "tenant.clerk.accounts.dev#fragment",
      "user@tenant.clerk.accounts.dev",
      "tenant.clerk.accounts.dev:8443",
      "tenant.clerk.accounts.dev; script-src 'unsafe-inline'",
      "*.clerk.accounts.dev",
      "localhost",
      "clerk.local",
      "203.0.113.10",
      "single-label",
      " tenant.clerk.accounts.dev",
    ]) {
      expect(() => resolveClerkDomain(clerkDomain)).toThrow(
        "NEXT_PUBLIC_CLERK_DOMAIN",
      );
    }
  });
});
