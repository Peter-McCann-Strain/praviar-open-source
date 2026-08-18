import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthBoundaryTestBridge } from "@/components/auth/auth-boundary-test-bridge";
import {
  AUTH_SESSION_RECOVERY_TEST_EVENT,
  type AuthSessionRecoveryTestDetail,
} from "@/lib/auth-boundary-test-bridge";

describe("AuthBoundaryTestBridge", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.__praviarE2EEmitAuthBoundaryChanged;
    delete window.__praviarE2ESetAuthSessionRecovery;
  });

  it("does not expose the E2E auth boundary hook without the dev bypass flag", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "false");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");

    render(<AuthBoundaryTestBridge />);

    await Promise.resolve();
    expect(window.__praviarE2EEmitAuthBoundaryChanged).toBeUndefined();
    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();
  });

  it("does not expose the E2E auth boundary hook without the explicit bridge flag", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "false");

    render(<AuthBoundaryTestBridge />);

    await Promise.resolve();
    expect(window.__praviarE2EEmitAuthBoundaryChanged).toBeUndefined();
    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();
  });

  it("does not expose the E2E auth boundary hook in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");

    render(<AuthBoundaryTestBridge />);

    await Promise.resolve();
    expect(window.__praviarE2EEmitAuthBoundaryChanged).toBeUndefined();
    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();
  });

  it("exposes and cleans up the E2E auth boundary hook only in explicit dev bypass mode", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");

    const { unmount } = render(<AuthBoundaryTestBridge />);

    await waitFor(() => {
      expect(window.__praviarE2EEmitAuthBoundaryChanged).toEqual(
        expect.any(Function),
      );
      expect(window.__praviarE2ESetAuthSessionRecovery).toEqual(
        expect.any(Function),
      );
    });

    unmount();

    expect(window.__praviarE2EEmitAuthBoundaryChanged).toBeUndefined();
    expect(window.__praviarE2ESetAuthSessionRecovery).toBeUndefined();
  });

  it("emits only supported recovery states and clears them during cleanup", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEV_AUTH_BYPASS", "true");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_AUTH_BOUNDARY_TEST_BRIDGE", "true");
    const recoveryReasons: AuthSessionRecoveryTestDetail["reason"][] = [];
    const recordRecovery = (event: Event) => {
      recoveryReasons.push(
        (event as CustomEvent<AuthSessionRecoveryTestDetail>).detail.reason,
      );
    };
    window.addEventListener(AUTH_SESSION_RECOVERY_TEST_EVENT, recordRecovery);

    const { unmount } = render(<AuthBoundaryTestBridge />);

    await waitFor(() => {
      expect(window.__praviarE2ESetAuthSessionRecovery).toEqual(
        expect.any(Function),
      );
    });

    window.__praviarE2ESetAuthSessionRecovery?.("expired");
    window.__praviarE2ESetAuthSessionRecovery?.("refresh_failed");
    (
      window.__praviarE2ESetAuthSessionRecovery as
        | ((action: unknown) => void)
        | undefined
    )?.("unsupported");
    (
      window.__praviarE2ESetAuthSessionRecovery as
        | ((action: unknown) => void)
        | undefined
    )?.(null);

    expect(recoveryReasons).toEqual(["expired", "refresh_failed"]);

    unmount();

    expect(recoveryReasons).toEqual(["expired", "refresh_failed", null]);
    window.removeEventListener(
      AUTH_SESSION_RECOVERY_TEST_EVENT,
      recordRecovery,
    );
  });
});
