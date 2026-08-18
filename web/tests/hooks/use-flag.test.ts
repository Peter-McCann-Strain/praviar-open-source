import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));

import { useFlagAnalysis } from "@/hooks/use-flag";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useFlagAnalysis", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends POST to flag endpoint", async () => {
    mockApiClient.mockResolvedValueOnce({ flagged_for_review: true });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useFlagAnalysis("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("a1");
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/a1/flag",
      expect.objectContaining({
        method: "POST",
        token: "tok",
      }),
    );
  });

  it("returns flagged state on success", async () => {
    mockApiClient.mockResolvedValueOnce({ flagged_for_review: true });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useFlagAnalysis("tok"), { wrapper });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync("a1");
    });

    expect(response).toEqual({ flagged_for_review: true });
  });
});
