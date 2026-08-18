import { describe, expect, it } from "vitest";
import { validatedClerkDashboardUrl } from "@/lib/sso-dashboard-url";

describe("validatedClerkDashboardUrl", () => {
  const production = { demoMode: false };

  it("allows only the canonical Clerk organization SSO path", () => {
    expect(
      validatedClerkDashboardUrl(
        "https://dashboard.clerk.com/organizations/org_123/sso-connections",
        production,
      ),
    ).toBe("https://dashboard.clerk.com/organizations/org_123/sso-connections");
  });

  it.each([
    "https://evil.example/organizations/org_123/sso-connections",
    "https://dashboard.clerk.com.evil.example/organizations/org_123/sso-connections",
    "https://dashboard.clerk.com/apps/demo",
    "https://dashboard.clerk.com/organizations/org_123/sso-connections?next=https://evil.example",
    "https://dashboard.clerk.com/organizations/org_123/sso-connections#unexpected",
    "javascript:alert(1)",
    "//evil.example/organizations/org_123/sso-connections",
  ])("rejects untrusted destination %s", (value) => {
    expect(validatedClerkDashboardUrl(value, production)).toBeNull();
  });

  it("allows the exact same-origin demo handoff only in demo mode", () => {
    const options = {
      demoMode: true,
      currentOrigin: "https://app.praviar.example",
    };
    expect(
      validatedClerkDashboardUrl("/settings?demo_sso=clerk", options),
    ).toBe("/settings?demo_sso=clerk");
    expect(
      validatedClerkDashboardUrl(
        "https://app.praviar.example/settings?demo_sso=clerk",
        options,
      ),
    ).toBe("/settings?demo_sso=clerk");
    expect(
      validatedClerkDashboardUrl("/settings?demo_sso=clerk", production),
    ).toBeNull();
    expect(
      validatedClerkDashboardUrl(
        "https://evil.example/settings?demo_sso=clerk",
        options,
      ),
    ).toBeNull();
  });
});
