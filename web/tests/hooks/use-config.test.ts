import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));

import {
  useConfigPresets,
  useCreatePreset,
  useOrgDefaultConfig,
} from "@/hooks/use-config";
import { apiClient } from "@/lib/api-client";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useConfigPresets", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is disabled when token is null", () => {
    const { result } = renderHook(() => useConfigPresets(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches presets when token provided", async () => {
    const data = [{ id: "p1", name: "Quick", config: {} }];
    mockApiClient.mockResolvedValueOnce(data);
    const { result } = renderHook(() => useConfigPresets("tok"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
  });
});

describe("useOrgDefaultConfig", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is disabled when token is null", () => {
    const { result } = renderHook(() => useOrgDefaultConfig(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches organization defaults when token provided", async () => {
    const data = {
      config: { max_analysis_patents: 20 },
      can_manage: true,
    };
    mockApiClient.mockResolvedValueOnce(data);
    const { result } = renderHook(() => useOrgDefaultConfig("tok"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/configs/defaults",
      expect.objectContaining({ token: "tok" }),
    );
  });
});

describe("useCreatePreset", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends POST to create preset", async () => {
    mockApiClient.mockResolvedValueOnce({ id: "p2" });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCreatePreset("tok"), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        name: "Custom",
        config: { max_analysis_patents: 10 },
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/configs/presets",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });
});
