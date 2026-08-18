import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiClient, APIError } from "@/lib/api-client";
import {
  acceptAuthToken,
  emitAuthBoundaryChanged,
  getAuthBoundarySignal,
  setCurrentAuthBoundaryKey,
} from "@/lib/auth-events";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const AUTH_TOKEN = "accepted-test-token";

beforeEach(() => {
  mockFetch.mockReset();
  setCurrentAuthBoundaryKey("auth:test-boundary");
  acceptAuthToken(AUTH_TOKEN);
});

function mockResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("apiClient", () => {
  describe("successful requests", () => {
    it("makes a GET request and returns JSON", async () => {
      const data = { id: "123", name: "test" };
      mockFetch.mockResolvedValue(mockResponse(data));

      const result = await apiClient("/analyses", { token: AUTH_TOKEN });

      expect(result).toEqual(data);
      expect(mockFetch).toHaveBeenCalledOnce();
    });

    it("builds the correct URL with API_BASE_URL and /api/v1 prefix", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await apiClient("/analyses/123", { token: AUTH_TOKEN });

      const calledUrl = mockFetch.mock.calls[0][0];
      expect(calledUrl).toBe("http://localhost:8000/api/v1/analyses/123");
    });

    it("makes a POST request with body", async () => {
      const responseData = { id: "new-123" };
      mockFetch.mockResolvedValue(mockResponse(responseData, { status: 201 }));

      const result = await apiClient("/analyses", {
        method: "POST",
        body: JSON.stringify({ compound_input: "aspirin" }),
        token: AUTH_TOKEN,
      });

      expect(result).toEqual(responseData);
      const calledOptions = mockFetch.mock.calls[0][1];
      expect(calledOptions.method).toBe("POST");
    });

    it("returns undefined for 204 No Content", async () => {
      mockFetch.mockResolvedValue(
        new Response(null, { status: 204, statusText: "No Content" }),
      );

      const result = await apiClient("/analyses/123", {
        method: "DELETE",
        token: AUTH_TOKEN,
      });

      expect(result).toBeUndefined();
    });

    it("returns the runtime validator's parsed value", async () => {
      const validate = vi.fn().mockReturnValue({ id: "parsed" });
      mockFetch.mockResolvedValue(mockResponse({ id: "raw", ignored: true }));

      const result = await apiClient("/analyses/123", {
        token: AUTH_TOKEN,
        validate,
      });

      expect(validate).toHaveBeenCalledWith({ id: "raw", ignored: true });
      expect(result).toEqual({ id: "parsed" });
    });

    it("propagates runtime validation failures without retrying", async () => {
      const validationError = new Error("response contract failed");
      mockFetch.mockResolvedValue(mockResponse({ id: "malformed" }));

      await expect(
        apiClient("/analyses/123", {
          token: AUTH_TOKEN,
          maxRetries: 3,
          validate: () => {
            throw validationError;
          },
        }),
      ).rejects.toBe(validationError);
      expect(mockFetch).toHaveBeenCalledOnce();
    });
  });

  describe("error handling", () => {
    it("throws APIError on 404 with correct status", async () => {
      mockFetch.mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Not found" }), {
            status: 404,
            statusText: "Not Found",
          }),
        ),
      );

      await expect(
        apiClient("/analyses/nonexistent", { token: AUTH_TOKEN }),
      ).rejects.toMatchObject({
        name: "APIError",
        status: 404,
        message: "The requested resource was not found.",
      });
    });

    it("throws APIError on 500 with status", async () => {
      mockFetch.mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Internal server error" }), {
            status: 500,
            statusText: "Internal Server Error",
          }),
        ),
      );

      await expect(
        apiClient("/analyses", { maxRetries: 0, token: AUTH_TOKEN }),
      ).rejects.toMatchObject({
        name: "APIError",
        status: 500,
        message: "The service is temporarily unavailable. Please try again.",
      });
    });

    it("handles non-JSON error response body gracefully", async () => {
      mockFetch.mockImplementation(() =>
        Promise.resolve(
          new Response("Internal Server Error", {
            status: 500,
            statusText: "Internal Server Error",
            headers: { "Content-Type": "text/plain" },
          }),
        ),
      );

      await expect(
        apiClient("/analyses", { maxRetries: 0, token: AUTH_TOKEN }),
      ).rejects.toMatchObject({
        name: "APIError",
        status: 500,
        message: "The service is temporarily unavailable. Please try again.",
      });
    });

    it("keeps RFC 9457 correlation while excluding remote detail and body fields", async () => {
      const remoteDetail = [
        "provider secret: raw failure",
        "database detail must stay hidden",
        "counsel@example.test",
        "token=remote-token-value",
      ].join(" ");
      mockFetch.mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "https://problems.praviar.invalid/service-unavailable",
            title: "Remote title must not become the Error message",
            status: 503,
            detail: remoteDetail,
            instance: "/internal/database/path",
            request_id: "body-request-id",
            correlation_id: "correlation-safe-123",
            provider_payload: { secret: "raw-provider-body" },
          }),
          {
            status: 503,
            headers: {
              "Content-Type": "application/problem+json",
              "X-Request-ID": "header-request-id",
            },
          },
        ),
      );

      const error = await apiClient("/analyses", {
        maxRetries: 0,
        token: AUTH_TOKEN,
      }).catch((caught: unknown) => caught);

      expect(error).toBeInstanceOf(APIError);
      expect(error).toMatchObject({
        message: "The service is temporarily unavailable. Please try again.",
        data: {
          type: "https://problems.praviar.invalid/service-unavailable",
          request_id: "header-request-id",
          correlation_id: "correlation-safe-123",
        },
        telemetry: {
          status: 503,
          errorClass: "APIError",
          typeUri: "https://problems.praviar.invalid/service-unavailable",
          requestId: "header-request-id",
          correlationId: "correlation-safe-123",
        },
      });
      const exposed = JSON.stringify(error);
      expect(exposed).not.toContain(remoteDetail);
      expect(exposed).not.toContain("Remote title");
      expect(exposed).not.toContain("raw-provider-body");
      expect(exposed).not.toContain("/internal/database/path");
    });

    it("drops hostile type URIs and correlation identifiers", async () => {
      mockFetch.mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "https://problems.praviar.invalid@evil.example/forbidden",
            detail: "database detail must stay hidden",
            request_id: "counsel@example.test",
            correlation_id: "token=remote-token-value",
          }),
          { status: 403 },
        ),
      );

      const error = await apiClient("/analyses", {
        token: AUTH_TOKEN,
      }).catch((caught: unknown) => caught);

      expect(error).toMatchObject({
        status: 403,
        data: undefined,
        telemetry: {
          status: 403,
          errorClass: "APIError",
        },
      });
      expect(JSON.stringify(error)).not.toContain("evil.example");
      expect(JSON.stringify(error)).not.toContain("counsel@example.test");
      expect(JSON.stringify(error)).not.toContain("remote-token-value");
    });
  });

  describe("headers", () => {
    it("sets Content-Type to application/json", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await apiClient("/public-reference");

      const calledOptions = mockFetch.mock.calls[0][1];
      const headers = calledOptions.headers as Headers;
      expect(headers.get("Content-Type")).toBe("application/json");
    });

    it("sets Authorization header when an accepted token is provided", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await apiClient("/test", { token: AUTH_TOKEN });

      const calledOptions = mockFetch.mock.calls[0][1];
      const headers = calledOptions.headers as Headers;
      expect(headers.get("Authorization")).toBe(`Bearer ${AUTH_TOKEN}`);
    });

    it("does not set Authorization header when no token is provided", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await apiClient("/public-reference");

      const calledOptions = mockFetch.mock.calls[0][1];
      const headers = calledOptions.headers as Headers;
      expect(headers.get("Authorization")).toBeNull();
    });

    it("rejects tokenless private requests before fetch", async () => {
      await expect(apiClient("/analyses")).rejects.toMatchObject({
        name: "APIError",
        status: 401,
        message: "Authentication required for private endpoints",
      });
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("does not pass token through to fetch options", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await apiClient("/test", { token: AUTH_TOKEN });

      const calledOptions = mockFetch.mock.calls[0][1];
      expect(calledOptions).not.toHaveProperty("token");
    });

    it("rejects unaccepted bearer tokens before fetch", async () => {
      await expect(
        apiClient("/test", { token: "my-secret-token" }),
      ).rejects.toThrow("Authentication boundary changed");
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });

  describe("retry behavior", () => {
    it("retries GET on 500 up to maxRetries", async () => {
      mockFetch
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ detail: "error" }), { status: 500 }),
        )
        .mockResolvedValueOnce(mockResponse({ ok: true }));

      // Real timers with short delay — maxRetries: 1 means one retry attempt
      const result = await apiClient("/flaky", {
        maxRetries: 1,
        token: AUTH_TOKEN,
      });
      expect(result).toEqual({ ok: true });
      expect(mockFetch).toHaveBeenCalledTimes(2);
    }, 10000);

    it("does not retry POST requests (non-idempotent)", async () => {
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: "error" }), { status: 500 }),
      );

      await expect(
        apiClient("/analyses", {
          method: "POST",
          body: "{}",
          token: AUTH_TOKEN,
        }),
      ).rejects.toThrow(APIError);

      // Only 1 call — no retries for POST
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("does not retry 4xx errors", async () => {
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: "bad" }), { status: 400 }),
      );

      await expect(apiClient("/test", { token: AUTH_TOKEN })).rejects.toThrow(
        APIError,
      );
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("throws after exhausting retries", async () => {
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: "error" }), { status: 502 }),
      );

      // maxRetries: 0 means no retries — throws immediately
      await expect(
        apiClient("/always-fail", { maxRetries: 0, token: AUTH_TOKEN }),
      ).rejects.toThrow(APIError);
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("timeout behavior", () => {
    it("aborts the request when timeout fires", async () => {
      vi.useFakeTimers();
      // Mock fetch that listens for abort and rejects accordingly
      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal!.addEventListener("abort", () => {
              reject(
                new DOMException("The operation was aborted", "AbortError"),
              );
            });
          }),
      );

      const promise = apiClient("/public-reference/slow-endpoint", {
        timeout: 5000,
      });

      // Advance time past the timeout threshold
      vi.advanceTimersByTime(5000);

      await expect(promise).rejects.toThrow();
      vi.useRealTimers();
    });

    it("rejects with AbortError name when timeout fires", async () => {
      vi.useFakeTimers();
      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal!.addEventListener("abort", () => {
              reject(
                new DOMException("The operation was aborted", "AbortError"),
              );
            });
          }),
      );

      const promise = apiClient("/public-reference/slow", { timeout: 100 });
      vi.advanceTimersByTime(100);

      try {
        await promise;
      } catch (err) {
        expect((err as DOMException).name).toBe("AbortError");
      }
      vi.useRealTimers();
    });

    it("does not timeout when timeout is set to 0", async () => {
      const data = { id: "ok" };
      mockFetch.mockResolvedValue(mockResponse(data));

      // timeout: 0 disables the timeout
      const result = await apiClient("/public-reference/no-timeout", {
        timeout: 0,
      });
      expect(result).toEqual(data);
    });

    it("clears the timeout on successful response", async () => {
      const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
      mockFetch.mockResolvedValue(mockResponse({ ok: true }));

      await apiClient("/public-reference/fast-endpoint", { timeout: 5000 });

      // clearTimeout should have been called in the finally block
      expect(clearTimeoutSpy).toHaveBeenCalled();
      clearTimeoutSpy.mockRestore();
    });

    it("clears the timeout even when request fails", async () => {
      const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: "Not found" }), {
          status: 404,
          statusText: "Not Found",
        }),
      );

      await expect(
        apiClient("/public-reference/missing", { timeout: 5000 }),
      ).rejects.toThrow(APIError);

      expect(clearTimeoutSpy).toHaveBeenCalled();
      clearTimeoutSpy.mockRestore();
    });
  });

  describe("external signal cancellation", () => {
    it("aborts when external AbortSignal is triggered", async () => {
      const controller = new AbortController();

      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal!.addEventListener("abort", () => {
              reject(
                new DOMException("The operation was aborted", "AbortError"),
              );
            });
          }),
      );

      const promise = apiClient("/public-reference/cancellable", {
        signal: controller.signal,
        timeout: 0,
      });

      // Abort externally
      controller.abort();

      await expect(promise).rejects.toThrow();
    });

    it("supports external signal with custom abort reason", async () => {
      const controller = new AbortController();

      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal!.addEventListener("abort", () => {
              reject(new DOMException("Cancelled by user", "AbortError"));
            });
          }),
      );

      const promise = apiClient("/public-reference/cancellable", {
        signal: controller.signal,
        timeout: 0,
      });
      controller.abort("User navigated away");

      await expect(promise).rejects.toThrow();
    });

    it("passes the abort signal to fetch", async () => {
      const controller = new AbortController();
      mockFetch.mockResolvedValue(mockResponse({ ok: true }));

      await apiClient("/public-reference/test", { signal: controller.signal });

      const calledOptions = mockFetch.mock.calls[0][1];
      // The signal passed to fetch should be an AbortSignal (from the internal controller)
      expect(calledOptions.signal).toBeInstanceOf(AbortSignal);
    });

    it("aborts authenticated in-flight requests when the auth boundary changes", async () => {
      acceptAuthToken("old-token");
      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal!.addEventListener("abort", () => {
              reject(
                new DOMException(
                  "Authentication boundary changed",
                  "AbortError",
                ),
              );
            });
          }),
      );

      const promise = apiClient("/comments", {
        method: "POST",
        body: "{}",
        token: "old-token",
        timeout: 0,
      });

      emitAuthBoundaryChanged({ refreshToken: false });

      await expect(promise).rejects.toThrow();
      expect((mockFetch.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(
        true,
      );
    });

    it("cleans up auth boundary abort listeners after authenticated requests finish", async () => {
      emitAuthBoundaryChanged();
      acceptAuthToken("scoped-token");
      const authBoundarySignal = getAuthBoundarySignal();
      const addListenerSpy = vi.spyOn(authBoundarySignal, "addEventListener");
      const removeListenerSpy = vi.spyOn(
        authBoundarySignal,
        "removeEventListener",
      );
      mockFetch.mockResolvedValue(mockResponse({ ok: true }));

      await apiClient("/comments", {
        token: "scoped-token",
        timeout: 0,
      });

      const abortListener = addListenerSpy.mock.calls.find(
        ([eventName]) => eventName === "abort",
      )?.[1];

      expect(abortListener).toEqual(expect.any(Function));
      expect(removeListenerSpy).toHaveBeenCalledWith("abort", abortListener);
    });

    it("does not abort tokenless public requests on auth boundary changes", async () => {
      let capturedSignal: AbortSignal | undefined;
      mockFetch.mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((resolve) => {
            capturedSignal = init.signal ?? undefined;
            setTimeout(() => {
              resolve(mockResponse({ ok: true }));
            }, 0);
          }),
      );

      const promise = apiClient("/public-reference", { timeout: 0 });
      emitAuthBoundaryChanged({ refreshToken: false });

      await expect(promise).resolves.toEqual({ ok: true });
      expect(capturedSignal?.aborted).toBe(false);
    });

    it("rejects old-token requests created after an auth boundary change", async () => {
      acceptAuthToken("old-token");
      emitAuthBoundaryChanged({ refreshToken: false });

      await expect(
        apiClient("/comments", {
          method: "POST",
          body: "{}",
          token: "old-token",
          timeout: 0,
        }),
      ).rejects.toThrow("Authentication boundary changed");
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("rejects tokens accepted under a previous Clerk boundary key", async () => {
      setCurrentAuthBoundaryKey("auth:scope:org-a");
      acceptAuthToken("same-sub-token");
      setCurrentAuthBoundaryKey("auth:scope:org-b");

      await expect(
        apiClient("/comments", {
          method: "POST",
          body: "{}",
          token: "same-sub-token",
          timeout: 0,
        }),
      ).rejects.toThrow("Authentication boundary changed");
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("still rejects old-token requests after mounted hooks clear accepted token", async () => {
      acceptAuthToken("old-token");
      emitAuthBoundaryChanged({ refreshToken: false });
      acceptAuthToken(null);

      await expect(
        apiClient("/comments", {
          method: "POST",
          body: "{}",
          token: "old-token",
          timeout: 0,
        }),
      ).rejects.toThrow("Authentication boundary changed");
      expect(mockFetch).not.toHaveBeenCalled();
    });

    it("allows authenticated requests after the refreshed token is accepted", async () => {
      emitAuthBoundaryChanged();
      acceptAuthToken("new-token");
      mockFetch.mockResolvedValue(mockResponse({ ok: true }));

      await expect(
        apiClient("/comments", {
          method: "POST",
          body: "{}",
          token: "new-token",
          timeout: 0,
        }),
      ).resolves.toEqual({ ok: true });
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
  });
});

describe("APIError", () => {
  it("has the correct name", () => {
    const error = new APIError(404, "Not found");
    expect(error.name).toBe("APIError");
  });

  it("stores status and message", () => {
    const error = new APIError(500, "Server error");
    expect(error.status).toBe(500);
    expect(error.message).toBe("Server error");
    expect(error.telemetry).toEqual({
      status: 500,
      errorClass: "APIError",
    });
  });

  it("stores optional data", () => {
    const data = { detail: "Something went wrong" };
    const error = new APIError(400, "Bad request", data);
    expect(error.data).toEqual(data);
  });

  it("is an instance of Error", () => {
    const error = new APIError(404, "Not found");
    expect(error).toBeInstanceOf(Error);
  });
});
