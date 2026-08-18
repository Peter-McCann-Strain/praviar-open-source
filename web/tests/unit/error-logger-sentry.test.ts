import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sentryMocks = vi.hoisted(() => ({
  captureException: vi.fn(),
  init: vi.fn(),
}));

vi.mock("@sentry/browser", () => ({
  captureException: sentryMocks.captureException,
  init: sentryMocks.init,
}));

describe("Sentry API error telemetry", () => {
  beforeEach(() => {
    vi.resetModules();
    sentryMocks.captureException.mockReset();
    sentryMocks.init.mockReset();
    vi.stubEnv(
      "NEXT_PUBLIC_SENTRY_DSN",
      "https://public@example.ingest.sentry.io/123",
    );
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("captures only the API error correlation envelope", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { APIError } = await import("@/lib/api-client");
    const { logError } = await import("@/lib/error-logger");
    const error = new APIError(
      503,
      "provider secret: raw failure; database detail must stay hidden; counsel@example.test",
      {
        detail: "token=remote-token-value",
        provider_payload: "raw response body",
      },
      {
        typeUri: "https://problems.praviar.invalid/service-unavailable",
        requestId: "request-safe-123",
        correlationId: "correlation-safe-456",
      },
    );

    logError(error, {
      source: "apiClient",
      extra: {
        responseBody: "database detail must stay hidden",
        providerSecret: "raw failure",
      },
    });

    await vi.waitFor(() => {
      expect(sentryMocks.captureException).toHaveBeenCalledOnce();
    });
    const [capturedError, options] = sentryMocks.captureException.mock.calls[0];
    expect(capturedError).toBeInstanceOf(Error);
    expect(capturedError).toMatchObject({
      name: "APIError",
      message: "APIError",
    });
    expect(options).toEqual({
      tags: { source: "apiClient" },
      extra: {
        status: 503,
        errorClass: "APIError",
        typeUri: "https://problems.praviar.invalid/service-unavailable",
        requestId: "request-safe-123",
        correlationId: "correlation-safe-456",
      },
      level: "error",
    });
    const captured = JSON.stringify(sentryMocks.captureException.mock.calls);
    expect(captured).not.toContain("provider secret");
    expect(captured).not.toContain("raw failure");
    expect(captured).not.toContain("database detail must stay hidden");
    expect(captured).not.toContain("counsel@example.test");
    expect(captured).not.toContain("remote-token-value");
    expect(captured).not.toContain("raw response body");
  });
});
