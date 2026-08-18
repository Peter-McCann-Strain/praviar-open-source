import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return { ...actual, apiClient: apiClientMock };
});
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "demo-token",
}));
vi.mock("@/lib/constants", () => ({ DEMO_MODE_ENABLED: true }));

import {
  useExternalSharingPolicy,
  useUpdateExternalSharingPolicy,
} from "@/hooks/use-external-sharing-policy";
import type { ExternalSharingPolicyUpdate } from "@/hooks/use-external-sharing-policy";

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

describe("external sharing policy demo contract", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requires a versioned impact preview before synthetic destructive enforcement", async () => {
    const wrapper = createWrapper();
    const policy = renderHook(() => useExternalSharingPolicy(), { wrapper });
    const update = renderHook(() => useUpdateExternalSharingPolicy(), {
      wrapper,
    });

    await waitFor(() => expect(policy.result.current.isSuccess).toBe(true));
    expect(policy.result.current.data).toMatchObject({
      mode: "approved_domains_only",
      approved_domains: [],
      version: 1,
    });

    let opened: ExternalSharingPolicyUpdate | undefined;
    await act(async () => {
      opened = await update.result.current.mutateAsync({
        mode: "open",
        approved_domains: [],
        expected_version: 1,
        confirm_destructive: false,
      });
    });
    expect(opened).toMatchObject({ status: "applied", version: 2 });

    let preview: ExternalSharingPolicyUpdate | undefined;
    await act(async () => {
      preview = await update.result.current.mutateAsync({
        mode: "approved_domains_only",
        approved_domains: ["outside-counsel.example"],
        expected_version: 2,
        confirm_destructive: false,
      });
    });
    expect(preview).toMatchObject({
      status: "confirmation_required",
      version: 2,
      impact: {
        active_grant_count: 1,
        pending_grant_count: 1,
        total_grant_count: 2,
      },
    });
    expect(preview?.proposal_digest).toHaveLength(64);

    let applied: ExternalSharingPolicyUpdate | undefined;
    await act(async () => {
      applied = await update.result.current.mutateAsync({
        mode: "approved_domains_only",
        approved_domains: ["outside-counsel.example"],
        expected_version: 2,
        confirm_destructive: true,
        proposal_digest: preview?.proposal_digest ?? undefined,
      });
    });
    expect(applied).toMatchObject({
      status: "applied",
      version: 3,
      revoked_grant_count: 2,
    });
    expect(apiClientMock).not.toHaveBeenCalled();
  });
});
