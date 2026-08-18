import { describe, it, expect, vi, beforeEach } from "vitest";
import { APIError } from "@/lib/api-client";
import { logError, initErrorReporting } from "@/lib/error-logger";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("logError", () => {
  describe("basic logging", () => {
    it("calls console.error", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("Something went wrong");
      expect(spy).toHaveBeenCalledOnce();
    });

    it("includes the error message in console output", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("Connection failed");
      expect(spy).toHaveBeenCalledWith(
        expect.any(String),
        "Connection failed",
        expect.anything(),
      );
    });
  });

  describe("source context", () => {
    it("includes source in the log prefix", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("Fetch failed", { source: "apiClient" });
      expect(spy).toHaveBeenCalledWith(
        "[apiClient]",
        "Fetch failed",
        expect.anything(),
      );
    });

    it("defaults source to 'unknown' when not provided", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("Generic error");
      expect(spy).toHaveBeenCalledWith(
        "[unknown]",
        "Generic error",
        expect.anything(),
      );
    });

    it("defaults source to 'unknown' when context is undefined", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("No context", undefined);
      expect(spy).toHaveBeenCalledWith(
        "[unknown]",
        "No context",
        expect.anything(),
      );
    });
  });

  describe("Error objects", () => {
    it("extracts message from Error instances", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const error = new Error("Network timeout");
      logError(error, { source: "fetchWrapper" });
      expect(spy).toHaveBeenCalledWith(
        "[fetchWrapper]",
        "Network timeout",
        expect.anything(),
      );
    });

    it("handles TypeError instances", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const error = new TypeError("Cannot read properties of undefined");
      logError(error);
      expect(spy).toHaveBeenCalledWith(
        "[unknown]",
        "Cannot read properties of undefined",
        expect.anything(),
      );
    });
  });

  describe("string errors", () => {
    it("handles plain string errors", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("A plain string error");
      expect(spy).toHaveBeenCalledWith(
        "[unknown]",
        "A plain string error",
        expect.anything(),
      );
    });

    it("converts non-string non-Error values to strings", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError(42);
      expect(spy).toHaveBeenCalledWith("[unknown]", "42", expect.anything());
    });

    it("converts null to string", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError(null);
      expect(spy).toHaveBeenCalledWith("[unknown]", "null", expect.anything());
    });

    it("converts undefined to string", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError(undefined);
      expect(spy).toHaveBeenCalledWith(
        "[unknown]",
        "undefined",
        expect.anything(),
      );
    });
  });

  describe("extra metadata", () => {
    it("includes extra metadata in the log output", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const extra = { endpoint: "/api/v1/analyses", statusCode: 500 };
      logError("Server error", { source: "apiClient", extra });
      expect(spy).toHaveBeenCalledWith("[apiClient]", "Server error", extra);
    });

    it("logs empty string when no extra metadata is provided", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("No extras", { source: "test" });
      expect(spy).toHaveBeenCalledWith("[test]", "No extras", "");
    });

    it("handles complex nested extra metadata", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const extra = {
        request: { method: "POST", url: "/analyses" },
        response: { status: 422, errors: ["Invalid SMILES"] },
      };
      logError("Validation failed", { source: "form", extra });
      expect(spy).toHaveBeenCalledWith("[form]", "Validation failed", extra);
    });

    it("redacts diagnostic details from console message and metadata", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError(
        new Error(
          "postgres://secret-host/praviar sk_live_secret SELECT * FROM analyses Traceback worker stack",
        ),
        {
          source: "apiClient",
          extra: {
            endpoint: "/api/v1/analyses",
            sql: "SELECT * FROM audit_log",
            nested: {
              token: "Bearer abc123",
              path: "/Users/example-user/praviar/app.ts",
            },
          },
        },
      );

      expect(spy).toHaveBeenCalledWith(
        "[apiClient]",
        expect.stringContaining("[redacted connection string]"),
        expect.objectContaining({
          sql: "[redacted query]",
          nested: expect.objectContaining({
            token: "[redacted metadata]",
            path: "[redacted path]",
          }),
        }),
      );
      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("postgres://secret-host");
      expect(output).not.toContain("sk_live_secret");
      expect(output).not.toContain("SELECT * FROM");
      expect(output).not.toContain("/Users/example-user");
    });

    it("redacts confidential metadata by key even when the value looks ordinary", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("Search failed", {
        source: "reportSearch",
        extra: {
          analysisId: "ana-safe",
          query: "unpublished-candidate-PRV-142",
          compoundInput: "CC(=O)Oc1ccccc1C(=O)O",
          nested: { reviewerEmail: "counsel@example.test" },
        },
      });

      const output = JSON.stringify(spy.mock.calls);
      expect(output).toContain("ana-safe");
      expect(output).not.toContain("unpublished-candidate-PRV-142");
      expect(output).not.toContain("CC(=O)Oc1ccccc1C(=O)O");
      expect(output).not.toContain("counsel@example.test");
      expect(output).toContain("[redacted metadata]");
    });

    it("redacts arbitrary remote body and error-message metadata by key", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError(new Error("Operation failed"), {
        source: "remoteBoundary",
        extra: {
          responseBody: "UNPUBLISHED_ASSET_PRV_142",
          errorMessage: "Novel compound program must stay private",
          nested: { detail: "Provider returned confidential evidence" },
        },
      });

      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("UNPUBLISHED_ASSET_PRV_142");
      expect(output).not.toContain("Novel compound program");
      expect(output).not.toContain("confidential evidence");
      expect(output).toContain("[redacted metadata]");
    });

    it("redacts generic key-value credentials and email PII in free text", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      logError("provider secret: raw failure", {
        source: "provider",
        extra: {
          detail: 'password="ordinary words that must stay hidden"',
          note: "api-key: key-material-that-must-stay-hidden",
          contact: "Escalate to counsel@example.test",
        },
      });

      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("raw failure");
      expect(output).not.toContain("ordinary words");
      expect(output).not.toContain("key-material");
      expect(output).not.toContain("counsel@example.test");
      expect(output).toContain("[redacted]");
      expect(output).toContain("[redacted email]");
    });

    it("logs API errors through a closed correlation-only envelope", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const error = new APIError(
        503,
        "provider secret: raw failure; database detail must stay hidden; counsel@example.test",
        {
          detail: "token=remote-token-value",
          body: "raw response body",
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

      expect(spy).toHaveBeenCalledWith("[apiClient]", "APIError", {
        status: 503,
        errorClass: "APIError",
        typeUri: "https://problems.praviar.invalid/service-unavailable",
        requestId: "request-safe-123",
        correlationId: "correlation-safe-456",
      });
      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("provider secret");
      expect(output).not.toContain("raw failure");
      expect(output).not.toContain("database detail must stay hidden");
      expect(output).not.toContain("counsel@example.test");
      expect(output).not.toContain("remote-token-value");
      expect(output).not.toContain("raw response body");
    });

    it("drops hostile optional API telemetry fields without falling back to Error.message", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const error = new APIError(
        500,
        "database detail must stay hidden",
        undefined,
        {
          typeUri:
            "https://praviar.io@evil.example/errors/internal-server-error",
          requestId: "counsel@example.test",
          correlationId: "token=remote-token-value",
        },
      );

      logError(error, { source: "apiClient" });

      expect(spy).toHaveBeenCalledWith("[apiClient]", "APIError", {
        status: 500,
        errorClass: "APIError",
      });
      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("evil.example");
      expect(output).not.toContain("database detail must stay hidden");
      expect(output).not.toContain("counsel@example.test");
      expect(output).not.toContain("remote-token-value");
    });

    it("does not leak an API error nested inside generic telemetry metadata", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});

      logError(new Error("Outer operation failed"), {
        source: "operation",
        extra: {
          cause: new APIError(
            502,
            "provider secret: raw failure; database detail must stay hidden",
          ),
        },
      });

      expect(spy).toHaveBeenCalledWith(
        "[operation]",
        "Outer operation failed",
        { cause: { name: "APIError", status: 502 } },
      );
      const output = JSON.stringify(spy.mock.calls);
      expect(output).not.toContain("provider secret");
      expect(output).not.toContain("raw failure");
      expect(output).not.toContain("database detail must stay hidden");
    });
  });
});

describe("initErrorReporting", () => {
  it("does not throw when DSN is not configured", async () => {
    await expect(initErrorReporting()).resolves.toBeUndefined();
  });

  it("is safe to call multiple times", async () => {
    await initErrorReporting();
    await initErrorReporting();
    // No errors thrown
  });
});
