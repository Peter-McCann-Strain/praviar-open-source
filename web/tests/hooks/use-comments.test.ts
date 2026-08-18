import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));

import { useComments, useCreateComment } from "@/hooks/use-comments";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useComments", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is disabled when token is null", () => {
    const { result } = renderHook(() => useComments("a1", null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("is disabled when analysisId is empty", () => {
    const { result } = renderHook(() => useComments("", "tok"), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches comments for analysis", async () => {
    const data = [{ id: "c1", body: "test" }];
    mockApiClient.mockResolvedValueOnce(data);
    const { result } = renderHook(() => useComments("a1", "tok"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/comments?analysis_id=a1",
      expect.objectContaining({ token: "tok" }),
    );
  });
});

describe("useCreateComment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends POST with body", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "c1" });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreateComment("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ analysis_id: "a1", body: "hello" });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/comments",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ analysis_id: "a1", body: "hello" }),
      }),
    );
  });
});
