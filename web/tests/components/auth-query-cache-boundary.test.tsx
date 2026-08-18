import { render } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  AuthBoundaryEventCacheReset,
  AuthQueryCacheBoundary,
  buildAuthBoundarySnapshot,
} from "@/components/auth/auth-query-cache-boundary";
import { AUTH_BOUNDARY_CHANGED_EVENT } from "@/lib/auth-events";
import { useConfigStore } from "@/stores/config-store";

type MockAuthState = {
  isLoaded: boolean;
  isSignedIn: boolean | undefined;
  userId: string | null;
  sessionId: string | null;
  orgId: string | null;
  orgRole: string | null;
  orgSlug: string | null;
  sessionClaims: Record<string, unknown>;
};

const authMock = vi.hoisted(() => ({
  value: {
    isLoaded: true,
    isSignedIn: true,
    userId: "user-a",
    sessionId: "session-a",
    orgId: "org-a",
    orgRole: "org:admin",
    orgSlug: "alpha",
    sessionClaims: {},
  } as MockAuthState,
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => authMock.value,
}));

describe("AuthQueryCacheBoundary", () => {
  beforeEach(() => {
    useConfigStore.getState().reset();
    authMock.value = {
      isLoaded: true,
      isSignedIn: true,
      userId: "user-a",
      sessionId: "session-a",
      orgId: "org-a",
      orgRole: "org:admin",
      orgSlug: "alpha",
      sessionClaims: {},
    };
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it("preserves rehydrated configuration on first initialization, then clears it on an org change", () => {
    const queryClient = new QueryClient();
    useConfigStore.getState().setConfig({ searchMaxRankedResults: 500 });
    window.localStorage.setItem(
      "praviar:config-auth-boundary",
      buildAuthBoundarySnapshot(authMock.value).key,
    );

    const { rerender } = render(
      <AuthQueryCacheBoundary queryClient={queryClient} />,
    );
    expect(useConfigStore.getState().searchMaxRankedResults).toBe(500);

    authMock.value = {
      ...authMock.value,
      orgId: "org-b",
      orgSlug: "beta",
    };
    rerender(<AuthQueryCacheBoundary queryClient={queryClient} />);

    expect(useConfigStore.getState().searchMaxRankedResults).toBe(200);
  });

  it("removes confidential checkout drafts when an auth-boundary event fires", () => {
    const queryClient = new QueryClient();
    window.localStorage.setItem(
      "praviar:analysis-launch-draft:ld_durable123",
      "durable confidential compound",
    );
    window.sessionStorage.setItem(
      "praviar:analysis-launch-draft:ld_secure123",
      "confidential compound",
    );

    render(<AuthBoundaryEventCacheReset queryClient={queryClient} />);
    window.dispatchEvent(new CustomEvent(AUTH_BOUNDARY_CHANGED_EVENT));

    expect(
      window.localStorage.getItem(
        "praviar:analysis-launch-draft:ld_durable123",
      ),
    ).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("preserves same-org persisted config while Clerk moves from loading to signed in", () => {
    const queryClient = new QueryClient();
    const boundaryEvents: CustomEvent<{ refreshToken: boolean }>[] = [];
    const recordBoundaryEvent = (event: Event) => {
      boundaryEvents.push(event as CustomEvent<{ refreshToken: boolean }>);
    };
    window.addEventListener(AUTH_BOUNDARY_CHANGED_EVENT, recordBoundaryEvent);
    const signedInSnapshot = buildAuthBoundarySnapshot(authMock.value);
    window.localStorage.setItem(
      "praviar:config-auth-boundary",
      signedInSnapshot.key,
    );
    useConfigStore.getState().setConfig({ searchMaxRankedResults: 500 });
    authMock.value = {
      ...authMock.value,
      isLoaded: false,
      isSignedIn: undefined,
    };

    const { rerender } = render(
      <AuthQueryCacheBoundary queryClient={queryClient} />,
    );
    expect(useConfigStore.getState().searchMaxRankedResults).toBe(500);

    authMock.value = {
      isLoaded: true,
      isSignedIn: true,
      userId: "user-a",
      sessionId: "session-a",
      orgId: "org-a",
      orgRole: "org:admin",
      orgSlug: "alpha",
      sessionClaims: {},
    };
    rerender(<AuthQueryCacheBoundary queryClient={queryClient} />);

    expect(useConfigStore.getState().searchMaxRankedResults).toBe(500);
    expect(boundaryEvents).toHaveLength(1);
    expect(boundaryEvents[0]?.detail).toEqual({ refreshToken: true });
    window.removeEventListener(
      AUTH_BOUNDARY_CHANGED_EVENT,
      recordBoundaryEvent,
    );
  });
});
