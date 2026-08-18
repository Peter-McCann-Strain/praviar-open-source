import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));

import { useSubmitFeedback } from "@/hooks/use-feedback";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useSubmitFeedback", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends POST with feedback payload", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "f1",
      analysis_id: "a1",
      created_at: "2026-01-01",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSubmitFeedback("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        analysis_id: "a1",
        overall_accuracy: 85,
        risk_level_correct: true,
        corrections: [],
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/feedback",
      expect.objectContaining({
        method: "POST",
        token: "tok",
      }),
    );
  });

  it("uses undefined token when null", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "f1",
      analysis_id: "a1",
      created_at: "2026-01-01",
    });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useSubmitFeedback(null), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        analysis_id: "a1",
        overall_accuracy: 90,
        risk_level_correct: true,
        corrections: [],
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/feedback",
      expect.objectContaining({
        token: undefined,
      }),
    );
  });
});
