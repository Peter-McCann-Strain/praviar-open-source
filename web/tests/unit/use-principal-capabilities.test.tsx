import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: false,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

import {
  canAccessWorkspaceHref,
  type PrincipalCapabilities,
  usePrincipalCapabilities,
} from "@/hooks/use-principal-capabilities";

const ADMIN_CAPABILITIES: PrincipalCapabilities = {
  role: "admin",
  can_create_analysis: true,
  can_view_patents: true,
  can_manage_monitors: true,
  can_view_review_queue: true,
  can_assign_review: true,
  can_resolve_review: true,
  can_escalate_review: true,
  can_create_batch: true,
  can_manage_config: true,
  can_export_report: true,
  can_share_report: true,
  can_deliver_report: true,
  can_view_billing: true,
  can_manage_billing: true,
  can_manage_api_keys: true,
  can_view_platform_admin: true,
  risk_ratings_restricted: false,
  api_key_report_export_scope_available: false,
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("usePrincipalCapabilities", () => {
  beforeEach(() => {
    mockApiClient.mockReset();
  });

  it("drops a cached privilege snapshot when its refresh fails", async () => {
    mockApiClient
      .mockResolvedValueOnce(ADMIN_CAPABILITIES)
      .mockRejectedValueOnce(new Error("authorization service unavailable"));

    const { result } = renderHook(
      () => usePrincipalCapabilities("test-token"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.data).toEqual(ADMIN_CAPABILITIES);
    });

    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
      expect(result.current.data).toBeUndefined();
    });
  });
});

describe("canAccessWorkspaceHref", () => {
  it("fails closed for patent and full-report routes without current authority", () => {
    expect(
      canAccessWorkspaceHref(
        {
          role: "scientist",
          can_view_patents: false,
          risk_ratings_restricted: true,
        },
        "/patents",
      ),
    ).toBe(false);
    expect(
      canAccessWorkspaceHref(
        {
          role: "scientist",
          can_view_patents: true,
          risk_ratings_restricted: true,
        },
        "/analyses/analysis-1/report?section=claims",
      ),
    ).toBe(false);
    expect(
      canAccessWorkspaceHref(
        {
          role: "scientist",
          risk_ratings_restricted: true,
        },
        "/analyses/analysis-1/report/summary",
      ),
    ).toBe(true);
  });
});
