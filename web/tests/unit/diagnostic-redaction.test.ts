import { describe, expect, it } from "vitest";
import { sanitizeDiagnosticText } from "@/lib/diagnostic-redaction";

describe("sanitizeDiagnosticText", () => {
  it("redacts SQL UPDATE statements with a SET clause", () => {
    expect(
      sanitizeDiagnosticText(
        "Database failed: UPDATE auth.users SET secret = 'private' WHERE id = 7",
        "Unavailable",
      ),
    ).toBe("Database failed: [redacted query]");
  });

  it("preserves ordinary operational prose containing update", () => {
    expect(
      sanitizeDiagnosticText(
        "[SSOSettings] Failed to update SSO configuration",
        "Unavailable",
      ),
    ).toBe("[SSOSettings] Failed to update SSO configuration");
  });
});
