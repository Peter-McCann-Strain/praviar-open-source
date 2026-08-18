import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
const clerkPublishableKey = (mode: "test" | "live", payload: string) =>
  ["pk", mode, payload].join("_");
const VALID_TEST_CLERK_KEY = clerkPublishableKey(
  "test",
  [
    "Zm9v",
    "LWJh",
    "ci0x",
    "My5j",
    "bGVy",
    "ay5h",
    "Y2Nv",
    "dW50",
    "cy5k",
    "ZXYk",
  ].join(""),
);

describe("useAuthToken", () => {
  describe("when Clerk is not configured", () => {
    beforeEach(() => {
      delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
      delete process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS;
      vi.resetModules();
    });

    afterEach(() => {
      delete process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS;
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
      vi.unstubAllEnvs();
    });

    it("returns demo-token without Clerk warnings when demo mode is enabled", async () => {
      process.env.NEXT_PUBLIC_DEMO_MODE = "true";
      const consoleWarnSpy = vi
        .spyOn(console, "warn")
        .mockImplementation(() => {});
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { isAuthTokenAccepted } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      expect(result.current).toBe("demo-token");
      expect(isAuthTokenAccepted("demo-token")).toBe(true);
      expect(consoleWarnSpy).not.toHaveBeenCalled();
      expect(consoleErrorSpy).not.toHaveBeenCalled();

      consoleWarnSpy.mockRestore();
      consoleErrorSpy.mockRestore();
    });

    it("keeps demo-token across clear-only auth boundary events", async () => {
      process.env.NEXT_PUBLIC_DEMO_MODE = "true";
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged, isAuthTokenAccepted } =
        await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: false });
      });

      expect(result.current).toBe("demo-token");
      expect(isAuthTokenAccepted("demo-token")).toBe(true);
    });

    it("returns null when dev auth bypass is not explicitly enabled", async () => {
      const consoleSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());
      expect(result.current).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("dev auth bypass disabled"),
      );
      consoleSpy.mockRestore();
    });

    it("returns dev-token immediately when dev auth bypass is explicitly enabled", async () => {
      process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS = "true";
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());
      expect(result.current).toBe("dev-token");
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("explicit dev-token bypass"),
      );
      consoleSpy.mockRestore();
    });

    it("logs console information about explicit dev-token bypass in development", async () => {
      process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS = "true";
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      renderHook(() => useAuthToken());
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("explicit dev-token bypass"),
      );
      consoleSpy.mockRestore();
    });

    it("returns the same dev-token across multiple renders when bypass is explicit", async () => {
      process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS = "true";
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result, rerender } = renderHook(() => useAuthToken());
      expect(result.current).toBe("dev-token");
      rerender();
      expect(result.current).toBe("dev-token");
      expect(consoleSpy).toHaveBeenCalledTimes(1);
      consoleSpy.mockRestore();
    });

    it("drops the dev-token on a clear-only auth boundary event", async () => {
      process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS = "true";
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged, isAuthTokenAccepted } =
        await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());
      expect(result.current).toBe("dev-token");

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: false });
      });

      expect(result.current).toBeNull();
      expect(isAuthTokenAccepted("dev-token")).toBe(false);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("explicit dev-token bypass"),
      );
      consoleSpy.mockRestore();
    });

    it("reaccepts the dev-token on a refreshable auth boundary event", async () => {
      process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS = "true";
      const consoleSpy = vi.spyOn(console, "info").mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged, isAuthTokenAccepted } =
        await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: false });
      });
      expect(result.current).toBeNull();

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: true });
      });

      expect(result.current).toBe("dev-token");
      expect(isAuthTokenAccepted("dev-token")).toBe(true);
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("explicit dev-token bypass"),
      );
      consoleSpy.mockRestore();
    });

    it("fails loud in production without logging malformed Clerk key values", async () => {
      vi.stubEnv("NODE_ENV", "production");
      vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.praviar.example");
      vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_abc");
      vi.resetModules();
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      expect(result.current).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("Clerk publishable key missing or invalid"),
      );
      const loggedText = consoleSpy.mock.calls.flat().join(" ");
      expect(loggedText).not.toContain("pk_test_abc");
      expect(loggedText).not.toContain("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=");
      consoleSpy.mockRestore();
    });
  });

  describe("when Clerk is configured but session is unavailable", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = VALID_TEST_CLERK_KEY;
      vi.resetModules();
      delete (window as any).Clerk;
    });

    afterEach(() => {
      vi.useRealTimers();
      delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    });

    it("returns null initially when Clerk key is present", async () => {
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());
      expect(result.current).toBeNull();
    });

    it("returns null and logs error after backoff exhausts if Clerk never initializes", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      // Advance through exponential backoff: 500 + 1000 + 2000 + 4000 = 7500ms total
      // After 4s delay, pollDelay becomes 8000 which exceeds 5000 cutoff → gives up
      await act(async () => {
        vi.advanceTimersByTime(10000);
      });

      expect(result.current).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        "[useAuthToken]",
        expect.stringContaining("did not initialize within"),
        expect.anything(),
      );
      consoleSpy.mockRestore();
    });
  });

  describe("when Clerk is configured and session is available", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = VALID_TEST_CLERK_KEY;
      vi.resetModules();
    });

    afterEach(() => {
      vi.useRealTimers();
      delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
      delete (window as any).Clerk;
    });

    it("retrieves token from Clerk session once loaded", async () => {
      (window as any).Clerk = {
        loaded: true,
        session: {
          getToken: vi.fn().mockResolvedValue("clerk-jwt-token"),
        },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      // First poll fires at 500ms (exponential backoff starts at 500ms)
      await act(async () => {
        vi.advanceTimersByTime(600);
      });

      expect(result.current).toBe("clerk-jwt-token");
    });

    it("sets token to null when Clerk getToken returns null", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      (window as any).Clerk = {
        loaded: true,
        session: {
          getToken: vi.fn().mockResolvedValue(null),
        },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });

      expect(result.current).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("Clerk session returned null token"),
      );
      consoleSpy.mockRestore();
    });

    it("sets token to null when Clerk getToken throws", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      (window as any).Clerk = {
        loaded: true,
        session: {
          getToken: vi.fn().mockRejectedValue(new Error("network error")),
        },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });

      expect(result.current).toBeNull();
      expect(consoleSpy).toHaveBeenCalledWith(
        "[useAuthToken]",
        "Clerk token refresh failed",
        expect.objectContaining({
          action: "refresh_clerk_token",
          clerkLoaded: true,
          hasSession: true,
        }),
      );
      consoleSpy.mockRestore();
    });

    it("cleans up timers on unmount during polling", async () => {
      // Clerk session not yet available — hook will be polling
      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { unmount } = renderHook(() => useAuthToken());

      // Unmount while still polling (before Clerk initializes)
      unmount();

      // Advance timers — should not throw or set state after unmount
      await act(async () => {
        vi.advanceTimersByTime(10000);
      });
      // If cleanup didn't work, the above would cause React warnings about
      // setting state on an unmounted component. No error = pass.
    });

    it("polls with exponential backoff starting at 500ms", async () => {
      const getTokenMock = vi.fn().mockResolvedValue("token-after-delay");

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      // Clerk is not yet available — null initially
      expect(result.current).toBeNull();

      // Make Clerk available after some backoff cycles
      await act(async () => {
        vi.advanceTimersByTime(500); // first poll fires
      });
      // Still null because Clerk isn't loaded yet
      expect(result.current).toBeNull();

      // Now set up Clerk session
      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      // Next poll at 1000ms (doubled from 500)
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current).toBe("token-after-delay");
      expect(getTokenMock).toHaveBeenCalled();
    });

    it("sets up refresh interval after successful token retrieval", async () => {
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockResolvedValueOnce("refreshed-token");

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { result } = renderHook(() => useAuthToken());

      // First poll at 500ms gets the token
      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      // Refresh interval is 50_000ms (50 seconds)
      await act(async () => {
        vi.advanceTimersByTime(50_000);
      });
      expect(result.current).toBe("refreshed-token");
      expect(getTokenMock).toHaveBeenCalledTimes(2);
    });

    it("refreshes immediately when the auth boundary changes", async () => {
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockResolvedValueOnce("boundary-token");

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      await act(async () => {
        emitAuthBoundaryChanged();
        await Promise.resolve();
      });

      expect(result.current).toBe("boundary-token");
      expect(getTokenMock).toHaveBeenCalledTimes(2);
    });

    it("drops the old token while an auth boundary refresh is pending", async () => {
      let resolveBoundaryToken: (token: string) => void = () => {};
      const boundaryTokenPromise = new Promise<string>((resolve) => {
        resolveBoundaryToken = resolve;
      });
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockReturnValueOnce(boundaryTokenPromise);

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      await act(async () => {
        emitAuthBoundaryChanged();
      });

      expect(result.current).toBeNull();

      await act(async () => {
        resolveBoundaryToken("boundary-token");
        await Promise.resolve();
      });

      expect(result.current).toBe("boundary-token");
      expect(getTokenMock).toHaveBeenCalledTimes(2);
    });

    it("does not refresh from Clerk during a clear-only auth transition", async () => {
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockResolvedValueOnce("stale-transition-token");

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: false });
        await Promise.resolve();
      });

      expect(result.current).toBeNull();
      expect(getTokenMock).toHaveBeenCalledTimes(1);
    });

    it("keeps token cleared on later intervals during a clear-only transition", async () => {
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockResolvedValueOnce("stale-interval-token");

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      await act(async () => {
        emitAuthBoundaryChanged({ refreshToken: false });
        await Promise.resolve();
      });
      expect(result.current).toBeNull();

      await act(async () => {
        vi.advanceTimersByTime(50_000);
        await Promise.resolve();
      });

      expect(result.current).toBeNull();
      expect(getTokenMock).toHaveBeenCalledTimes(1);
    });

    it("ignores stale async refreshes from an older auth boundary", async () => {
      let resolveOldRefresh: (token: string) => void = () => {};
      const oldRefreshPromise = new Promise<string>((resolve) => {
        resolveOldRefresh = resolve;
      });
      const getTokenMock = vi
        .fn()
        .mockResolvedValueOnce("first-token")
        .mockReturnValueOnce(oldRefreshPromise)
        .mockResolvedValueOnce("boundary-token");

      (window as any).Clerk = {
        loaded: true,
        session: { getToken: getTokenMock },
      };

      const { useAuthToken } = await import("@/hooks/use-auth-token");
      const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
      const { result } = renderHook(() => useAuthToken());

      await act(async () => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current).toBe("first-token");

      await act(async () => {
        vi.advanceTimersByTime(50_000);
      });
      expect(getTokenMock).toHaveBeenCalledTimes(2);
      expect(result.current).toBe("first-token");

      await act(async () => {
        emitAuthBoundaryChanged();
        await Promise.resolve();
      });
      expect(result.current).toBe("boundary-token");

      await act(async () => {
        resolveOldRefresh("stale-token");
        await Promise.resolve();
      });

      expect(result.current).toBe("boundary-token");
      expect(getTokenMock).toHaveBeenCalledTimes(3);
    });
  });
});
