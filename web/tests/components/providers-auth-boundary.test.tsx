import React, { useEffect } from "react";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AUTH_BOUNDARY_CHANGED_EVENT } from "@/lib/auth-events";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useReviewStore } from "@/stores/review-store";

const mockUseAuth = vi.fn();

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/hooks/use-clerk-session", () => ({
  hasClerk: true,
}));

import { Providers } from "@/app/providers";

function signedInAuth(overrides: Record<string, unknown> = {}) {
  return {
    isLoaded: true,
    isSignedIn: true,
    userId: "user_1",
    sessionId: "sess_1",
    orgId: "org_1",
    orgRole: "org:admin",
    orgSlug: "acme",
    sessionClaims: {
      sub: "user_1",
      sid: "sess_1",
      org_id: "org_1",
      org_role: "org:admin",
    },
    ...overrides,
  };
}

function QueryClientProbe({
  onClient,
}: {
  onClient: (client: QueryClient) => void;
}) {
  const queryClient = useQueryClient();

  useEffect(() => {
    onClient(queryClient);
  }, [onClient, queryClient]);

  return null;
}

describe("Providers auth boundary cache hygiene", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePipelineStore.getState().reset();
    useReviewStore.getState().resetAll();
    mockUseAuth.mockReturnValue(signedInAuth());
  });

  it("keeps cache on stable auth boundary renders", async () => {
    let queryClient: QueryClient | null = null;
    const boundaryListener = vi.fn();
    window.addEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);

    const { rerender } = render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());
    queryClient!.setQueryData(["reports", "analysis-1", "scope-a"], {
      report_id: "private-report",
    });

    rerender(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    expect(
      queryClient!.getQueryData(["reports", "analysis-1", "scope-a"]),
    ).toEqual({
      report_id: "private-report",
    });
    expect(boundaryListener).not.toHaveBeenCalled();

    window.removeEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);
  });

  it("clears cached private data and emits refresh when the org boundary changes", async () => {
    let queryClient: QueryClient | null = null;
    const boundaryListener = vi.fn();
    window.addEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);

    const { rerender } = render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());
    queryClient!.setQueryData(["billing", "status", "scope-a"], {
      plan: "enterprise",
    });
    queryClient!.setQueryData(["public-reference-data"], {
      version: "2026-06",
    });
    expect(queryClient!.getQueryCache().findAll()).toHaveLength(2);

    mockUseAuth.mockReturnValue(
      signedInAuth({
        orgId: "org_2",
        orgSlug: "globex",
        sessionClaims: {
          sub: "user_1",
          sid: "sess_1",
          org_id: "org_2",
          org_role: "org:admin",
        },
      }),
    );

    rerender(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() =>
      expect(queryClient!.getQueryCache().findAll()).toHaveLength(1),
    );
    expect(
      queryClient!.getQueryData(["billing", "status", "scope-a"]),
    ).toBeUndefined();
    expect(queryClient!.getQueryData(["public-reference-data"])).toEqual({
      version: "2026-06",
    });
    expect(boundaryListener).toHaveBeenCalledTimes(1);
    expect((boundaryListener.mock.calls[0][0] as CustomEvent).detail).toEqual({
      refreshToken: true,
    });

    window.removeEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);
  });

  it("resets private client stores when the org boundary changes", async () => {
    let queryClient: QueryClient | null = null;

    const { rerender } = render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());

    usePipelineStore.getState().setStepStatus(2, "running", {
      description: "Searching private patent corpus",
    });
    usePipelineStore.getState().setError("private pipeline error");
    useReviewStore
      .getState()
      .overrideRisk(
        "analysis-1",
        "US123",
        "high",
        "private reviewer note",
        "user-1",
      );

    expect(usePipelineStore.getState().currentStep).toBe(2);
    expect(usePipelineStore.getState().error).toBe("private pipeline error");
    expect(
      useReviewStore.getState().getReview("analysis-1", "US123")?.notes,
    ).toBe("private reviewer note");

    mockUseAuth.mockReturnValue(
      signedInAuth({
        orgId: "org_2",
        orgSlug: "globex",
        sessionClaims: {
          sub: "user_1",
          sid: "sess_1",
          org_id: "org_2",
          org_role: "org:admin",
        },
      }),
    );

    rerender(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => {
      expect(usePipelineStore.getState().currentStep).toBe(0);
    });
    expect(usePipelineStore.getState().error).toBeNull();
    expect(useReviewStore.getState().getAnalysisReviews("analysis-1")).toEqual(
      {},
    );
  });

  it("clears private cache while Clerk is still loading a known transition", async () => {
    let queryClient: QueryClient | null = null;
    const boundaryListener = vi.fn();
    window.addEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);

    const { rerender } = render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());
    queryClient!.setQueryData(["reports", "analysis-1", "scope-a"], {
      report_id: "private-report",
    });

    mockUseAuth.mockReturnValue(
      signedInAuth({
        isLoaded: false,
        orgId: "org_2",
        sessionClaims: {
          sub: "user_1",
          sid: "sess_1",
          org_id: "org_2",
          org_role: "org:admin",
        },
      }),
    );

    rerender(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() =>
      expect(queryClient!.getQueryCache().findAll()).toHaveLength(0),
    );
    expect(
      queryClient!.getQueryData(["reports", "analysis-1", "scope-a"]),
    ).toBeUndefined();
    expect(boundaryListener).toHaveBeenCalledTimes(1);
    expect((boundaryListener.mock.calls[0][0] as CustomEvent).detail).toEqual({
      refreshToken: false,
    });

    window.removeEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);
  });

  it("clears cached private data on sign-out", async () => {
    let queryClient: QueryClient | null = null;
    const boundaryListener = vi.fn();
    window.addEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);

    const { rerender } = render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());
    queryClient!.setQueryData(["api-keys", 1, "scope-a"], {
      items: [{ prefix: "sk_live_secret" }],
    });
    queryClient!.setQueryData(["public-reference-data"], {
      version: "2026-06",
    });

    mockUseAuth.mockReturnValue({
      isLoaded: true,
      isSignedIn: false,
      userId: null,
      sessionId: null,
      orgId: null,
      orgRole: null,
      orgSlug: null,
      sessionClaims: null,
    });

    rerender(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() =>
      expect(queryClient!.getQueryCache().findAll()).toHaveLength(1),
    );
    expect(
      queryClient!.getQueryData(["api-keys", 1, "scope-a"]),
    ).toBeUndefined();
    expect(queryClient!.getQueryData(["public-reference-data"])).toEqual({
      version: "2026-06",
    });
    expect(boundaryListener).toHaveBeenCalledTimes(1);
    expect((boundaryListener.mock.calls[0][0] as CustomEvent).detail).toEqual({
      refreshToken: false,
    });

    window.removeEventListener(AUTH_BOUNDARY_CHANGED_EVENT, boundaryListener);
  });
});
