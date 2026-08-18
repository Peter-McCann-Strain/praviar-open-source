import { describe, expect, it } from "vitest";
import {
  consoleDiagnosticSetDiff,
  exactConsoleDiagnosticIdentity,
} from "../e2e/fixtures/visual-matrix-console-diagnostics";

describe("visual matrix exact console diagnostic contract", () => {
  const expected = [
    "error: [mutation] Checkout provider unavailable",
    "error: [BillingPage] Failed to start credit checkout",
  ];

  it("derives a stable identity from app-owned source and message arguments", () => {
    expect(
      exactConsoleDiagnosticIdentity({
        args: [
          "[mutation]",
          "Checkout provider unavailable",
          { mutationKey: "ignored provenance" },
        ],
        fallbackText: "unused",
        type: "error",
      }),
    ).toBe("error: [mutation] Checkout provider unavailable");
  });

  it("fails closed when one expected diagnostic is missing", () => {
    expect(consoleDiagnosticSetDiff(expected.slice(0, 1), expected)).toEqual({
      missing: ["error: [BillingPage] Failed to start credit checkout"],
      unexpected: [],
    });
  });

  it("fails closed on an extra diagnostic", () => {
    expect(
      consoleDiagnosticSetDiff(
        [...expected, "error: [mutation] Unrelated failure"],
        expected,
      ),
    ).toEqual({
      missing: [],
      unexpected: ["error: [mutation] Unrelated failure"],
    });
  });

  it("treats diagnostics as a multiset so duplicate emission fails", () => {
    expect(
      consoleDiagnosticSetDiff(
        [expected[0]!, expected[0]!, expected[1]!],
        expected,
      ),
    ).toEqual({
      missing: [],
      unexpected: [expected[0]],
    });

    expect(
      consoleDiagnosticSetDiff(expected.slice(0, 1), [
        expected[0]!,
        expected[0]!,
      ]),
    ).toEqual({
      missing: [expected[0]],
      unexpected: [],
    });
  });

  it("rejects a hostile diagnostic that only shares the expected prefix", () => {
    expect(
      consoleDiagnosticSetDiff(
        [
          "error: [mutation] Checkout provider unavailable but state changed",
          expected[1]!,
        ],
        expected,
      ),
    ).toEqual({
      missing: ["error: [mutation] Checkout provider unavailable"],
      unexpected: [
        "error: [mutation] Checkout provider unavailable but state changed",
      ],
    });
  });

  it("fails closed when a profile-level diagnostic is globally swallowed", () => {
    const profileExpected = [
      "warning: [useAuthToken] DEV MODE: Clerk not configured",
    ];

    expect(consoleDiagnosticSetDiff([], profileExpected)).toEqual({
      missing: profileExpected,
      unexpected: [],
    });
  });
});
