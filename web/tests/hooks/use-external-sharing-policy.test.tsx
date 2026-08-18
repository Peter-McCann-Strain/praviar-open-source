import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api-client", () => ({ apiClient: apiClientMock }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));
vi.mock("@/lib/constants", () => ({ DEMO_MODE_ENABLED: false }));

import {
  useExternalSharingPolicy,
  useUpdateExternalSharingPolicy,
} from "@/hooks/use-external-sharing-policy";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("external sharing policy hooks", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the authenticated organization policy", async () => {
    const policy = {
      mode: "approved_domains_only" as const,
      approved_domains: ["approved.example"],
      version: 3,
    };
    apiClientMock.mockResolvedValueOnce(policy);
    const { result } = renderHook(() => useExternalSharingPolicy(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(policy);
    expect(apiClientMock).toHaveBeenCalledWith(
      "/admin/external-sharing-policy",
      expect.objectContaining({ token: "test-token" }),
    );
  });

  it("patches only the typed exact-domain payload", async () => {
    const payload = {
      mode: "approved_domains_only" as const,
      approved_domains: ["approved.example"],
      expected_version: 3,
      confirm_destructive: true,
      proposal_digest: "d".repeat(64),
    };
    apiClientMock.mockResolvedValueOnce({
      ...payload,
      version: 4,
      status: "applied",
      impact: {
        active_grant_count: 2,
        pending_grant_count: 1,
        total_grant_count: 3,
      },
      proposal_digest: null,
      revoked_grant_count: 3,
    });
    const { result } = renderHook(() => useUpdateExternalSharingPolicy(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(payload);
    });

    expect(apiClientMock).toHaveBeenCalledWith(
      "/admin/external-sharing-policy",
      {
        token: "test-token",
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  });
});
