import { describe, expect, it, vi } from "vitest";
import {
  installVisualMatrixFixedTime,
  installVisualMatrixHttpCacheBypass,
  installVisualMatrixSurfaceRandomness,
  resetVisualMatrixBrowserState,
  VISUAL_MATRIX_FIXED_TIME,
} from "../e2e/fixtures/visual-matrix-browser-isolation";

const onboardingKeys = {
  tour: "praviar:onboarding:test:tour",
  welcome: "praviar:onboarding:test:welcome",
};

function pageDouble(url: string) {
  const clearCookies = vi.fn().mockResolvedValue(undefined);
  const clearPermissions = vi.fn().mockResolvedValue(undefined);
  const evaluate = vi.fn().mockResolvedValue(undefined);
  return {
    clearCookies,
    clearPermissions,
    evaluate,
    page: {
      clock: { setFixedTime: vi.fn().mockResolvedValue(undefined) },
      context: () => ({ clearCookies, clearPermissions }),
      evaluate,
      url: () => url,
    },
  };
}

describe("visual matrix browser isolation", () => {
  it("freezes buyer-visible wall time without pausing browser timers", async () => {
    const testDouble = pageDouble("about:blank");

    await installVisualMatrixFixedTime(testDouble.page as never);

    expect(testDouble.page.clock.setFixedTime).toHaveBeenCalledWith(
      VISUAL_MATRIX_FIXED_TIME,
    );
  });

  it("clears persistent context and origin state before a surface", async () => {
    const testDouble = pageDouble("http://127.0.0.1:3000/dashboard");

    await resetVisualMatrixBrowserState(testDouble.page as never, {
      firstRun: false,
      onboardingKeys,
    });

    expect(testDouble.clearCookies).toHaveBeenCalledOnce();
    expect(testDouble.clearPermissions).toHaveBeenCalledOnce();
    expect(testDouble.evaluate).toHaveBeenCalledOnce();
    expect(testDouble.evaluate.mock.calls[0]?.[1]).toEqual({
      firstRun: false,
      onboardingKeys,
    });
  });

  it("does not attempt origin storage access from the initial blank page", async () => {
    const testDouble = pageDouble("about:blank");

    await resetVisualMatrixBrowserState(testDouble.page as never, {
      firstRun: false,
      onboardingKeys,
    });

    expect(testDouble.clearCookies).toHaveBeenCalledOnce();
    expect(testDouble.clearPermissions).toHaveBeenCalledOnce();
    expect(testDouble.evaluate).not.toHaveBeenCalled();
  });

  it("scopes deterministic randomness to the reveal document realm", async () => {
    const reveal = pageDouble("http://127.0.0.1:3000/settings");
    const followingSurface = pageDouble("http://127.0.0.1:3000/settings");

    await installVisualMatrixSurfaceRandomness(
      reveal.page as never,
      "settings-api-key-reveal",
    );
    await installVisualMatrixSurfaceRandomness(
      followingSurface.page as never,
      "settings-api-key-revoke-confirm",
    );

    expect(reveal.evaluate).toHaveBeenCalledOnce();
    expect(followingSurface.evaluate).not.toHaveBeenCalled();
  });

  it("installs a deterministic no-cache catch-all for each surface", async () => {
    const continueRequest = vi.fn().mockResolvedValue(undefined);
    const route = vi.fn().mockResolvedValue(undefined);
    const page = { route };

    await installVisualMatrixHttpCacheBypass(page as never);

    expect(route).toHaveBeenCalledOnce();
    expect(route.mock.calls[0]?.[0]).toBe("**/*");
    const handler = route.mock.calls[0]?.[1] as (
      requestRoute: unknown,
    ) => Promise<void>;
    await handler({
      continue: continueRequest,
      request: () => ({
        headers: () => ({
          accept: "text/html",
          "Cache-Control": "max-age=3600",
          Pragma: "cache",
        }),
      }),
    });

    expect(continueRequest).toHaveBeenCalledWith({
      headers: {
        accept: "text/html",
        "cache-control": "no-cache, no-store, max-age=0",
        pragma: "no-cache",
      },
    });
  });
});
