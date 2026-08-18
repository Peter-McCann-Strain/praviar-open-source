import { describe, expect, it } from "vitest";
import { sanitizePublicEvidenceUrl } from "@/app/share/[token]/public-evidence-url";
import { sanitizeDiagnosticText } from "@/lib/diagnostic-redaction";

describe("sanitizePublicEvidenceUrl", () => {
  it("normalizes an allowlisted public patent host", () => {
    expect(
      sanitizePublicEvidenceUrl(
        "https://WORLDWIDE.ESPACENET.COM/patent/search?q=US123#section",
      ),
    ).toBe("https://worldwide.espacenet.com/patent/search?q=US123");
  });

  it.each([
    "https://evil.example/phish",
    "https://127.0.0.1/admin",
    "https://[::1]/admin",
    "https://localhost/admin",
    "https://user:pass@patents.google.com/patent/US123",
    "https://patents.google.com.evil.example/patent/US123",
    "https://patents.google.com:8443/patent/US123",
    "http://patents.google.com/patent/US123",
  ])("rejects an untrusted public evidence authority: %s", (value) => {
    expect(sanitizePublicEvidenceUrl(value)).toBeNull();
  });
});

describe("namespaced API-key redaction", () => {
  it("redacts prv_live credentials from diagnostics", () => {
    const secret = `prv_live_${"a".repeat(43)}`;

    const sanitized = sanitizeDiagnosticText(
      `request failed for ${secret}`,
      "failed",
    );

    expect(sanitized).toContain("[redacted API key]");
    expect(sanitized).not.toContain(secret);
  });
});
