import { expect, test } from "./fixtures/strict-test";
import {
  assertStrongHsts,
  parseCspDirectives,
} from "./fixtures/browser-gate-policy";
import { waitForDeterministicSurface } from "./fixtures/surface-readiness";

const PUBLIC_PRODUCTION_ROUTES = [
  "/",
  "/sample-reports/example-molecule-alpha",
  "/methodology",
  "/trust",
] as const;

test("production CSP, nonce, hydration, and public surfaces are clean @production", async ({
  page,
}) => {
  const seenNonces = new Set<string>();
  for (const route of PUBLIC_PRODUCTION_ROUTES) {
    const response = await page.goto(route, { waitUntil: "domcontentloaded" });

    expect(response, `${route} returned a navigation response`).not.toBeNull();
    expect(response?.ok(), `${route} response status`).toBe(true);

    const headers = response?.headers() ?? {};
    const csp = headers["content-security-policy"];
    const nonce = headers["x-nonce"];
    expect(csp, `${route} CSP header`).toBeTruthy();
    expect(nonce, `${route} X-Nonce header`).toBeTruthy();
    if (!csp || !nonce) {
      throw new Error(`${route} did not return its CSP and nonce contract.`);
    }
    expect(csp).toContain(`'nonce-${nonce}'`);
    expect(seenNonces, `${route} uses a fresh response nonce`).not.toContain(
      nonce,
    );
    seenNonces.add(nonce);

    const directives = parseCspDirectives(csp);
    const defaultSrc = directives.get("default-src") ?? [];
    const scriptSrc = directives.get("script-src") ?? [];
    const connectSrc = directives.get("connect-src") ?? [];
    expect(defaultSrc, `${route} default-src remains closed`).toEqual([
      "'self'",
    ]);
    expect(scriptSrc, `${route} script-src exists`).not.toEqual([]);
    expect(scriptSrc).toContain("'self'");
    expect(scriptSrc).toContain("'wasm-unsafe-eval'");
    expect(scriptSrc).toContain(`'nonce-${nonce}'`);
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
    expect(scriptSrc).not.toContain("*");
    expect(scriptSrc).not.toContain("http:");
    expect(scriptSrc).not.toContain("https:");
    expect(connectSrc).not.toContain("*");
    expect(connectSrc).not.toContain("http:");
    expect(connectSrc).not.toContain("https:");
    expect(connectSrc).not.toContain("ws:");
    expect(connectSrc).not.toContain("wss:");
    expect(connectSrc.join(" ")).not.toMatch(
      /(?:localhost|127\.0\.0\.1|\[?::1\]?|0\.0\.0\.0|http:\/\/)/iu,
    );
    expect(directives.get("frame-ancestors")).toEqual(["'none'"]);

    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(() =>
      assertStrongHsts(headers["strict-transport-security"]),
    ).not.toThrow();

    const inlineScriptNonces = await page
      .locator("script:not([src])")
      .evaluateAll((scripts) => scripts.map((script) => script.nonce));
    expect(
      inlineScriptNonces.length,
      `${route} inline bootstrap scripts`,
    ).toBeGreaterThan(0);
    expect(
      inlineScriptNonces.every((scriptNonce) => scriptNonce === nonce),
      `${route} inline script nonces match the enforced CSP`,
    ).toBe(true);
    await waitForDeterministicSurface(page, `${route} production surface`);
    await expect(page.locator("html")).toHaveClass(/\blight\b/u);
  }
});
