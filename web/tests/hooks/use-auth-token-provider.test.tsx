import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const VALID_TEST_CLERK_KEY = [
  "pk",
  "test",
  "Zm9vLWJhci0xMy5jbGVyay5hY2NvdW50cy5kZXYk",
].join("_");

describe("AuthTokenProvider", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    delete (window as typeof window & { Clerk?: unknown }).Clerk;
    delete window.__praviarE2EEmitAuthBoundaryChanged;
    delete window.__praviarE2ESetAuthSessionRecovery;
    vi.resetModules();
  });

  async function renderRecoveryConsumer(getToken: ReturnType<typeof vi.fn>) {
    vi.useFakeTimers();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);
    vi.resetModules();
    (window as typeof window & { Clerk?: unknown }).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { AuthTokenProvider, useAuthSessionRecovery, useAuthToken } =
      await import("@/hooks/use-auth-token");

    function Consumer() {
      const token = useAuthToken();
      const recovery = useAuthSessionRecovery();

      return (
        <div>
          <span data-testid="token">{token ?? "pending"}</span>
          <span data-testid="reason">{recovery.reason ?? "none"}</span>
          <span data-testid="refreshing">
            {recovery.isRefreshing ? "refreshing" : "idle"}
          </span>
          <button type="button" onClick={recovery.retrySession}>
            Retry
          </button>
        </div>
      );
    }

    render(
      <AuthTokenProvider>
        <Consumer />
      </AuthTokenProvider>,
    );

    return {
      advance: async (milliseconds: number) => {
        await act(async () => {
          vi.advanceTimersByTime(milliseconds);
          await Promise.resolve();
        });
      },
    };
  }

  it("owns one Clerk refresh loop for multiple token consumers", async () => {
    vi.useFakeTimers();
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", VALID_TEST_CLERK_KEY);
    vi.resetModules();
    const getToken = vi.fn().mockResolvedValue("shared-token");
    (window as typeof window & { Clerk?: unknown }).Clerk = {
      loaded: true,
      session: { getToken },
    };

    const { AuthTokenProvider, useAuthToken } =
      await import("@/hooks/use-auth-token");
    function Consumer({ label }: { label: string }) {
      return <span>{`${label}:${useAuthToken() ?? "pending"}`}</span>;
    }

    render(
      <AuthTokenProvider>
        <Consumer label="a" />
        <Consumer label="b" />
      </AuthTokenProvider>,
    );
    await act(async () => {
      vi.advanceTimersByTime(600);
    });

    expect(screen.getByText("a:shared-token")).toBeInTheDocument();
    expect(screen.getByText("b:shared-token")).toBeInTheDocument();
    expect(getToken).toHaveBeenCalledTimes(1);
    expect(getToken).toHaveBeenCalledWith({ skipCache: true });
  });

  it("exposes durable recovery only after an accepted session expires", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("accepted-token")
      .mockResolvedValueOnce(null);
    const { advance } = await renderRecoveryConsumer(getToken);

    await advance(600);
    expect(screen.getByTestId("token")).toHaveTextContent("accepted-token");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");

    await advance(50_000);
    expect(screen.getByTestId("token")).toHaveTextContent("pending");
    expect(screen.getByTestId("reason")).toHaveTextContent("expired");

    const { useToastStore } = await import("@/stores/toast-store");
    expect(
      useToastStore
        .getState()
        .toasts.some((toast) => toast.message.includes("Session expired")),
    ).toBe(false);
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Clerk session returned null token"),
    );
  });

  it("keeps recovery visible while retrying and clears it on a fresh accepted token", async () => {
    let resolveRetry: (token: string) => void = () => {};
    const retryPromise = new Promise<string>((resolve) => {
      resolveRetry = resolve;
    });
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("accepted-token")
      .mockResolvedValueOnce(null)
      .mockReturnValueOnce(retryPromise);
    const { advance } = await renderRecoveryConsumer(getToken);

    await advance(600);
    await advance(50_000);
    expect(screen.getByTestId("reason")).toHaveTextContent("expired");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.getByTestId("reason")).toHaveTextContent("expired");
    expect(screen.getByTestId("refreshing")).toHaveTextContent("refreshing");
    expect(getToken).toHaveBeenLastCalledWith({ skipCache: true });

    await act(async () => {
      resolveRetry("fresh-token");
      await retryPromise;
    });

    expect(screen.getByTestId("token")).toHaveTextContent("fresh-token");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");
    expect(screen.getByTestId("refreshing")).toHaveTextContent("idle");
  });

  it("keeps a newer manual token when an older automatic refresh resolves later", async () => {
    let resolveAutomatic: (token: string | null) => void = () => {};
    const automaticPromise = new Promise<string | null>((resolve) => {
      resolveAutomatic = resolve;
    });
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("accepted-token")
      .mockReturnValueOnce(automaticPromise)
      .mockResolvedValueOnce("manual-fresh-token");
    const { advance } = await renderRecoveryConsumer(getToken);

    await advance(600);
    await advance(50_000);
    expect(getToken).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(getToken).toHaveBeenCalledTimes(3);
    expect(screen.getByTestId("token")).toHaveTextContent("manual-fresh-token");

    await act(async () => {
      resolveAutomatic(null);
      await automaticPromise;
    });

    expect(screen.getByTestId("token")).toHaveTextContent("manual-fresh-token");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");
  });

  it("does not label initial loading or a signed-out session as expired", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const getToken = vi.fn().mockResolvedValue(null);
    const { advance } = await renderRecoveryConsumer(getToken);

    expect(screen.getByTestId("token")).toHaveTextContent("pending");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");

    await advance(600);

    expect(screen.getByTestId("token")).toHaveTextContent("pending");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");
    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining("Clerk session returned null token"),
    );
  });

  it("clears recovery on signed-out and organization-boundary transitions", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("accepted-token")
      .mockResolvedValueOnce(null);
    const { advance } = await renderRecoveryConsumer(getToken);
    const { emitAuthBoundaryChanged } = await import("@/lib/auth-events");

    await advance(600);
    await advance(50_000);
    expect(screen.getByTestId("reason")).toHaveTextContent("expired");

    await act(async () => {
      emitAuthBoundaryChanged({ refreshToken: false });
      await Promise.resolve();
    });

    expect(screen.getByTestId("token")).toHaveTextContent("pending");
    expect(screen.getByTestId("reason")).toHaveTextContent("none");
    expect(getToken).toHaveBeenCalledTimes(2);
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("distinguishes an established-session refresh failure from initial auth failure", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const getToken = vi
      .fn()
      .mockResolvedValueOnce("accepted-token")
      .mockRejectedValueOnce(new Error("network down"));
    const { advance } = await renderRecoveryConsumer(getToken);

    await advance(600);
    await advance(50_000);

    expect(screen.getByTestId("reason")).toHaveTextContent("refresh_failed");
    const { useToastStore } = await import("@/stores/toast-store");
    expect(
      useToastStore
        .getState()
        .toasts.some((toast) =>
          toast.message.includes("Authentication failed"),
        ),
    ).toBe(false);
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("lets the gated browser bridge set exact recovery states without changing the token", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "");
    vi.resetModules();
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { AuthTokenProvider, useAuthSessionRecovery, useAuthToken } =
      await import("@/hooks/use-auth-token");
    const { AuthBoundaryTestBridge } =
      await import("@/components/auth/auth-boundary-test-bridge");

    function Consumer() {
      const token = useAuthToken();
      const recovery = useAuthSessionRecovery();
      return (
        <div>
          <span data-testid="bridge-token">{token ?? "pending"}</span>
          <span data-testid="bridge-reason">{recovery.reason ?? "none"}</span>
          <span data-testid="bridge-refreshing">
            {recovery.isRefreshing ? "refreshing" : "idle"}
          </span>
          <button type="button" onClick={recovery.retrySession}>
            Retry recovery
          </button>
        </div>
      );
    }

    render(
      <AuthTokenProvider>
        <AuthBoundaryTestBridge />
        <Consumer />
      </AuthTokenProvider>,
    );

    await waitFor(() => {
      expect(window.__praviarE2ESetAuthSessionRecovery).toEqual(
        expect.any(Function),
      );
    });
    expect(screen.getByTestId("bridge-token")).toHaveTextContent("dev-token");

    act(() => {
      window.__praviarE2ESetAuthSessionRecovery?.("expired");
    });
    expect(screen.getByTestId("bridge-reason")).toHaveTextContent("expired");
    expect(screen.getByTestId("bridge-token")).toHaveTextContent("pending");
    expect(screen.getByTestId("bridge-refreshing")).toHaveTextContent("idle");

    fireEvent.click(screen.getByRole("button", { name: "Retry recovery" }));
    await waitFor(() => {
      expect(screen.getByTestId("bridge-reason")).toHaveTextContent("none");
      expect(screen.getByTestId("bridge-token")).toHaveTextContent("dev-token");
    });

    act(() => {
      window.__praviarE2ESetAuthSessionRecovery?.("refresh_failed");
    });
    expect(screen.getByTestId("bridge-reason")).toHaveTextContent(
      "refresh_failed",
    );
    expect(screen.getByTestId("bridge-token")).toHaveTextContent("pending");

    act(() => {
      window.__praviarE2ESetAuthSessionRecovery?.("clear");
    });
    expect(screen.getByTestId("bridge-reason")).toHaveTextContent("none");
    expect(screen.getByTestId("bridge-token")).toHaveTextContent("dev-token");
  });

  it("clears injected recovery when the browser bridge unmounts", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "");
    vi.resetModules();
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { AuthTokenProvider, useAuthSessionRecovery } =
      await import("@/hooks/use-auth-token");
    const { AuthBoundaryTestBridge } =
      await import("@/components/auth/auth-boundary-test-bridge");

    function Consumer() {
      const recovery = useAuthSessionRecovery();
      return (
        <span data-testid="cleanup-reason">{recovery.reason ?? "none"}</span>
      );
    }
    function App({ bridgeVisible }: { bridgeVisible: boolean }) {
      return (
        <AuthTokenProvider>
          {bridgeVisible ? <AuthBoundaryTestBridge /> : null}
          <Consumer />
        </AuthTokenProvider>
      );
    }

    const view = render(<App bridgeVisible />);
    await waitFor(() => {
      expect(window.__praviarE2ESetAuthSessionRecovery).toEqual(
        expect.any(Function),
      );
    });

    act(() => {
      window.__praviarE2ESetAuthSessionRecovery?.("expired");
    });
    expect(screen.getByTestId("cleanup-reason")).toHaveTextContent("expired");

    view.rerender(<App bridgeVisible={false} />);

    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();
    expect(screen.getByTestId("cleanup-reason")).toHaveTextContent("none");
  });

  it("ignores recovery events when the explicit browser bridge gate is disabled", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "false");
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "");
    vi.resetModules();
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { AuthTokenProvider, useAuthSessionRecovery, useAuthToken } =
      await import("@/hooks/use-auth-token");
    const { AuthBoundaryTestBridge } =
      await import("@/components/auth/auth-boundary-test-bridge");
    const { AUTH_SESSION_RECOVERY_TEST_EVENT } =
      await import("@/lib/auth-boundary-test-bridge");

    function Consumer() {
      const token = useAuthToken();
      const recovery = useAuthSessionRecovery();
      return (
        <div>
          <span data-testid="disabled-bridge-token">{token ?? "pending"}</span>
          <span data-testid="disabled-bridge-reason">
            {recovery.reason ?? "none"}
          </span>
        </div>
      );
    }

    render(
      <AuthTokenProvider>
        <AuthBoundaryTestBridge />
        <Consumer />
      </AuthTokenProvider>,
    );

    await Promise.resolve();
    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();

    act(() => {
      window.dispatchEvent(
        new CustomEvent(AUTH_SESSION_RECOVERY_TEST_EVENT, {
          detail: { reason: "expired" },
        }),
      );
    });

    expect(screen.getByTestId("disabled-bridge-reason")).toHaveTextContent(
      "none",
    );
    expect(screen.getByTestId("disabled-bridge-token")).toHaveTextContent(
      "dev-token",
    );
  });
});
