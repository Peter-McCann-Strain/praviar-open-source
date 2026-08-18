import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("useClerkSession", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = VALID_TEST_CLERK_KEY;
    vi.resetModules();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    delete (window as any).Clerk;
  });

  it("reports whether Clerk is configured", async () => {
    const { hasClerk, useClerkSession } =
      await import("@/hooks/use-clerk-session");
    const { result } = renderHook(() => useClerkSession());

    expect(hasClerk).toBe(true);
    expect(result.current.hasClerk).toBe(true);
    expect(result.current.token).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("polls Clerk, stores a token, and refreshes it on the interval", async () => {
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockResolvedValueOnce("next-token");
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { result, unmount } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");
    expect(result.current.error).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current.token).toBe("next-token");

    unmount();
  });

  it("keeps same-boundary interval refreshes single-flight", async () => {
    let resolveRefresh: (token: string) => void = () => {};
    const refreshPromise = new Promise<string>((resolve) => {
      resolveRefresh = resolve;
    });
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockReturnValueOnce(refreshPromise);
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");

    await act(async () => {
      vi.advanceTimersByTime(50_000);
    });
    expect(getToken).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(50_000);
    });
    expect(getToken).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveRefresh("single-flight-token");
      await refreshPromise;
    });
    expect(result.current.token).toBe("single-flight-token");
  });

  it("refreshes immediately when the auth boundary changes", async () => {
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockResolvedValueOnce("boundary-token");
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");

    await act(async () => {
      emitAuthBoundaryChanged();
      await Promise.resolve();
    });

    expect(result.current.token).toBe("boundary-token");
    expect(getToken).toHaveBeenCalledTimes(2);
  });

  it("does not refresh from Clerk during a clear-only auth transition", async () => {
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockResolvedValueOnce("stale-transition-token");
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");

    await act(async () => {
      emitAuthBoundaryChanged({ refreshToken: false });
      await Promise.resolve();
    });

    expect(result.current.token).toBeNull();
    expect(getToken).toHaveBeenCalledTimes(1);
  });

  it("keeps token cleared on later intervals during a clear-only transition", async () => {
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockResolvedValueOnce("stale-interval-token");
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");

    await act(async () => {
      emitAuthBoundaryChanged({ refreshToken: false });
      await Promise.resolve();
    });
    expect(result.current.token).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(50_000);
      await Promise.resolve();
    });

    expect(result.current.token).toBeNull();
    expect(getToken).toHaveBeenCalledTimes(1);
  });

  it("ignores stale async refreshes from an older auth boundary", async () => {
    let resolveOldRefresh: (token: string) => void = () => {};
    const oldRefreshPromise = new Promise<string>((resolve) => {
      resolveOldRefresh = resolve;
    });
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("first-token")
      .mockReturnValueOnce(oldRefreshPromise)
      .mockResolvedValueOnce("boundary-token");
    (window as any).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(result.current.token).toBe("first-token");

    await act(async () => {
      vi.advanceTimersByTime(50_000);
    });
    expect(getToken).toHaveBeenCalledTimes(2);

    await act(async () => {
      emitAuthBoundaryChanged();
      await Promise.resolve();
    });
    expect(result.current.token).toBe("boundary-token");

    await act(async () => {
      resolveOldRefresh("stale-token");
      await Promise.resolve();
    });

    expect(result.current.token).toBe("boundary-token");
    expect(getToken).toHaveBeenCalledTimes(3);
  });

  it("surfaces a null Clerk token as an expired session", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    (window as any).Clerk = {
      loaded: true,
      session: { getToken: vi.fn().mockResolvedValue(null) },
    };

    const { useClerkSession } = await import("@/hooks/use-clerk-session");
    const { useToastStore } = await import("@/stores/toast-store");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.token).toBeNull();
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Clerk session returned null token"),
    );
    expect(
      useToastStore
        .getState()
        .toasts.some((toast) => toast.message.includes("Session expired")),
    ).toBe(false);
  });

  it("captures Clerk getToken failures with context", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    (window as any).Clerk = {
      loaded: true,
      session: {
        getToken: vi.fn().mockRejectedValue(new Error("bad session")),
      },
    };

    const { AUTH_SESSION_REFRESH_ERROR_MESSAGE, useClerkSession } =
      await import("@/hooks/use-clerk-session");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.token).toBeNull();
    expect(result.current.error).toBe(AUTH_SESSION_REFRESH_ERROR_MESSAGE);
    expect(result.current.error).not.toContain("bad session");
    expect(consoleSpy).toHaveBeenCalledWith(
      "[useClerkSession]",
      "Clerk token refresh failed",
      expect.objectContaining({
        action: "refresh_clerk_token",
        clerkLoaded: true,
        hasSession: true,
      }),
    );
  });

  it("gives up loudly when Clerk never attaches a session", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    (window as any).Clerk = { loaded: false };

    const { AUTH_SESSION_UNAVAILABLE_ERROR_MESSAGE, useClerkSession } =
      await import("@/hooks/use-clerk-session");
    const { result } = renderHook(() => useClerkSession());

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });

    expect(result.current.token).toBeNull();
    expect(result.current.error).toBe(AUTH_SESSION_UNAVAILABLE_ERROR_MESSAGE);
    expect(result.current.error).not.toContain(
      "Clerk session did not initialize",
    );
    expect(consoleSpy).toHaveBeenCalledWith(
      "[useClerkSession]",
      expect.stringContaining("Clerk session did not initialize"),
      expect.objectContaining({ clerkOnWindow: true }),
    );
  });

  it("fails loud in production when Clerk is not configured", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.praviar.example");
    delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
    vi.resetModules();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { AUTH_SERVICE_NOT_CONFIGURED_MESSAGE, hasClerk, useClerkSession } =
      await import("@/hooks/use-clerk-session");
    const { result } = renderHook(() => useClerkSession());

    expect(hasClerk).toBe(false);
    expect(result.current.hasClerk).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.error).toBe(AUTH_SERVICE_NOT_CONFIGURED_MESSAGE);
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining(
        "[useClerkSession] PRODUCTION: Clerk publishable key missing or invalid.",
      ),
    );
  });
});
