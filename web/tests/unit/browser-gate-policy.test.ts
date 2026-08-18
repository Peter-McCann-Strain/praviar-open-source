import { describe, expect, it } from "vitest";
import {
  assertStrongHsts,
  isAllowedConsoleError,
  isFatalConsoleDiagnostic,
  isProvenBenignNavigationReplacement,
  parseCspDirectives,
} from "../e2e/fixtures/browser-gate-policy";

describe("browser gate policy", () => {
  it("allows only explicitly scoped console-error prefixes", () => {
    expect(
      isAllowedConsoleError("[query] expected offline failure", ["[query]"]),
    ).toBe(true);
    expect(
      isAllowedConsoleError("unrelated runtime explosion", ["[query]"]),
    ).toBe(false);
  });

  it("fails unexpected warnings and preserves narrow scoped allowlists", () => {
    expect(
      isFatalConsoleDiagnostic({
        allowedErrorPrefixes: [],
        allowedWarningPrefixes: [],
        message: "dependency entered a degraded mode",
        type: "warning",
      }),
    ).toBe(true);
    expect(
      isFatalConsoleDiagnostic({
        allowedErrorPrefixes: [],
        allowedWarningPrefixes: ["[expected-offline]"],
        message: "[expected-offline] fixture warning",
        type: "warning",
      }),
    ).toBe(false);
    expect(
      isFatalConsoleDiagnostic({
        allowedErrorPrefixes: [],
        allowedWarningPrefixes: ["Hydration"],
        message: "Hydration failed during fixture rendering",
        type: "warning",
      }),
    ).toBe(true);
  });

  it("treats only a replaced document navigation abort as benign", () => {
    expect(
      isProvenBenignNavigationReplacement({
        currentUrl: "https://app.example.test/dashboard",
        errorText: "net::ERR_ABORTED",
        expectedReplacementUrl: "https://app.example.test/dashboard",
        isNavigationRequest: true,
        requestUrl: "https://app.example.test/analyses",
        resourceType: "document",
      }),
    ).toBe(true);

    for (const resourceType of ["script", "stylesheet", "font"]) {
      expect(
        isProvenBenignNavigationReplacement({
          currentUrl: "https://app.example.test/dashboard",
          errorText: "net::ERR_ABORTED",
          expectedReplacementUrl: "https://app.example.test/dashboard",
          isNavigationRequest: false,
          requestUrl: `https://app.example.test/asset.${resourceType}`,
          resourceType,
        }),
      ).toBe(false);
    }
  });

  it("rejects an aborted document unless its exact replacement is declared", () => {
    expect(
      isProvenBenignNavigationReplacement({
        currentUrl: "https://app.example.test/dashboard",
        errorText: "net::ERR_ABORTED",
        isNavigationRequest: true,
        requestUrl: "https://app.example.test/analyses",
        resourceType: "document",
      }),
    ).toBe(false);
    expect(
      isProvenBenignNavigationReplacement({
        currentUrl: "https://app.example.test/dashboard",
        errorText: "net::ERR_ABORTED",
        expectedReplacementUrl: "https://app.example.test/help",
        isNavigationRequest: true,
        requestUrl: "https://app.example.test/analyses",
        resourceType: "document",
      }),
    ).toBe(false);
  });

  it("requires a one-year HSTS policy with subdomain coverage", () => {
    expect(() =>
      assertStrongHsts("max-age=63072000; includeSubDomains; preload"),
    ).not.toThrow();
    expect(() => assertStrongHsts("max-age=0; includeSubDomains")).toThrow(
      "at least 31536000",
    );
    expect(() => assertStrongHsts("max-age=31536000")).toThrow(
      "include includeSubDomains",
    );
    expect(() =>
      assertStrongHsts("max-age=63072000; max-age=0; includeSubDomains"),
    ).toThrow("duplicate max-age");
    expect(() =>
      assertStrongHsts(
        "max-age=63072000; includeSubDomains; includeSubDomains",
      ),
    ).toThrow("duplicate includesubdomains");
    expect(() =>
      assertStrongHsts("max-age=63072000; preload; PRELOAD; includeSubDomains"),
    ).toThrow("duplicate preload");
  });

  it("parses CSP directives for deployed-response assertions", () => {
    const directives = parseCspDirectives(
      "default-src 'self'; script-src 'self' 'nonce-abc'; frame-ancestors 'none'",
    );

    expect(directives.get("default-src")).toEqual(["'self'"]);
    expect(directives.get("script-src")).toEqual(["'self'", "'nonce-abc'"]);
    expect(directives.get("frame-ancestors")).toEqual(["'none'"]);
  });

  it("rejects duplicate CSP directives instead of accepting a shadow policy", () => {
    expect(() =>
      parseCspDirectives(
        "default-src 'self'; script-src *; script-src 'self' 'nonce-abc'",
      ),
    ).toThrow("Duplicate CSP directive: script-src");
  });
});
