import type { Request, Response } from "@playwright/test";
import { describe, expect, it } from "vitest";
import { VisualMatrixApiTracker } from "../e2e/fixtures/visual-matrix-api-tracker";

const APPLICATION_API_ORIGIN = "http://localhost:18080";

function request(
  method: string,
  path: string,
  failure: string | null = null,
  origin = APPLICATION_API_ORIGIN,
): Pick<Request, "failure" | "method" | "url"> {
  return {
    failure: () => (failure ? { errorText: failure } : null),
    method: () => method,
    url: () => `${origin}${path}`,
  };
}

function response(
  apiRequest: Pick<Request, "failure" | "method" | "url">,
  status: number,
): Pick<Response, "ok" | "request" | "status" | "url"> {
  return {
    ok: () => status >= 200 && status < 300,
    request: () => apiRequest as Request,
    status: () => status,
    url: () => apiRequest.url(),
  };
}

describe("visual matrix post-action API tracker", () => {
  it("retains hostile sender GET, POST, and OPTIONS failures after a clean pre-action gate", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();

    const navigationRequest = request(
      "GET",
      "/api/v1/reports/ana_demo_001/share",
    );
    tracker.requestStarted(navigationRequest);
    tracker.responseReceived(response(navigationRequest, 200));
    tracker.requestFinished(navigationRequest);

    expect(tracker.pendingRequests.size).toBe(0);
    expect(tracker.failures).toEqual([]);

    for (const [method, status] of [
      ["GET", 503],
      ["OPTIONS", 403],
      ["POST", 500],
    ] as const) {
      const hostileRequest = request(
        method,
        "/api/v1/reports/ana_demo_001/share",
      );
      tracker.requestStarted(hostileRequest);
      tracker.responseReceived(response(hostileRequest, status));
      tracker.requestFinished(hostileRequest);
    }

    expect(tracker.pendingRequests.size).toBe(0);
    expect(tracker.requestCount).toBe(4);
    expect(tracker.failures).toEqual([
      "GET /api/v1/reports/ana_demo_001/share HTTP 503",
      "OPTIONS /api/v1/reports/ana_demo_001/share HTTP 403",
      "POST /api/v1/reports/ana_demo_001/share HTTP 500",
    ]);
  });

  it("records transport failures and ignores unrelated origins", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();
    const failedRequest = request(
      "POST",
      "/api/v1/reports/ana_demo_001/share",
      "net::ERR_FAILED",
    );
    const unrelatedRequest = request("GET", "/brand/praviar-mark.svg");

    tracker.requestStarted(unrelatedRequest);
    expect(tracker.pendingHttpRequests.size).toBe(1);
    tracker.requestFailed(unrelatedRequest);
    tracker.requestStarted(failedRequest);
    tracker.requestFailed(failedRequest);

    expect(tracker.pendingRequests.size).toBe(0);
    expect(tracker.pendingHttpRequests.size).toBe(0);
    expect(tracker.requestCount).toBe(1);
    expect(tracker.failures).toEqual([
      "POST /api/v1/reports/ana_demo_001/share net::ERR_FAILED",
    ]);
  });

  it("accepts only a cancelled GET superseded by a successful identical GET", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();
    const cancelled = request(
      "GET",
      "/api/v1/monitors?page=1&per_page=100",
      "net::ERR_ABORTED",
    );
    const replacement = request("GET", "/api/v1/monitors?page=1&per_page=100");

    tracker.requestStarted(cancelled);
    tracker.requestFailed(cancelled);
    expect(tracker.failures).toEqual(["GET /api/v1/monitors net::ERR_ABORTED"]);

    tracker.requestStarted(replacement);
    tracker.responseReceived(response(replacement, 200));
    tracker.requestFinished(replacement);

    expect(tracker.failures).toEqual([]);
  });

  it("keeps lone, mismatched-query, mutation, and non-abort cancellations failing", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();
    const successfulDifferentQuery = request(
      "GET",
      "/api/v1/monitors?page=2&per_page=100",
    );
    tracker.responseReceived(response(successfulDifferentQuery, 200));

    for (const failedRequest of [
      request(
        "GET",
        "/api/v1/monitors?page=1&per_page=100",
        "net::ERR_ABORTED",
      ),
      request("POST", "/api/v1/monitors", "net::ERR_ABORTED"),
      request("GET", "/api/v1/analyses", "net::ERR_FAILED"),
    ]) {
      tracker.requestStarted(failedRequest);
      tracker.requestFailed(failedRequest);
    }

    expect(tracker.failures).toEqual([
      "GET /api/v1/monitors net::ERR_ABORTED",
      "POST /api/v1/monitors net::ERR_ABORTED",
      "GET /api/v1/analyses net::ERR_FAILED",
    ]);
  });

  it("fails closed on non-API HTTP error responses", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();
    const missingChunk = request("GET", "/_next/static/chunks/missing.js");
    const cachedChunk = request("GET", "/_next/static/chunks/cached.js");

    tracker.responseReceived(response(cachedChunk, 304));
    tracker.requestStarted(missingChunk);
    tracker.responseReceived(response(missingChunk, 404));
    tracker.requestFinished(missingChunk);

    expect(tracker.failures).toEqual([]);
    expect(tracker.nonApiResponseFailures).toEqual([
      "GET http://localhost:18080/_next/static/chunks/missing.js HTTP 404",
    ]);
  });

  it("does not classify a cross-origin /api path as application API traffic", () => {
    const tracker = new VisualMatrixApiTracker(APPLICATION_API_ORIGIN);
    tracker.startSurface();
    const hostileThirdParty = request(
      "GET",
      "/api/telemetry",
      null,
      "https://telemetry.example",
    );

    tracker.requestStarted(hostileThirdParty);
    tracker.responseReceived(response(hostileThirdParty, 503));
    tracker.requestFinished(hostileThirdParty);

    expect(tracker.requestCount).toBe(0);
    expect(tracker.pendingRequests.size).toBe(0);
    expect(tracker.pendingHttpRequests.size).toBe(0);
    expect(tracker.failures).toEqual([]);
    expect(tracker.nonApiResponseFailures).toEqual([
      "GET https://telemetry.example/api/telemetry HTTP 503",
    ]);
  });
});
