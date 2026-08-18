import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/constants", () => ({
  ANALYSIS_POLL_INTERVAL_MS: 3000,
  DEMO_MODE_ENABLED: true,
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: mockApiClient,
}));

import {
  useAnalyses,
  useAnalysis,
  useCreateAnalysis,
} from "@/hooks/use-analysis";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

describe("useAnalyses in demo mode", () => {
  beforeEach(() => {
    mockApiClient.mockClear();
  });

  it("applies search, risk, and status filters without calling the API", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () =>
        useAnalyses(
          null,
          1,
          20,
          "completed",
          "medium",
          "Example Molecule Alpha",
        ),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0]?.compound_name).toBe(
      "Example Molecule Alpha",
    );
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.status_counts?.completed).toBe(1);
    expect(result.current.data?.status_counts?.running).toBe(0);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("keeps demo status counts scoped to search and risk before status filtering", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () =>
        useAnalyses(null, 1, 20, "running", "medium", "Example Molecule Alpha"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(0);
    expect(result.current.data?.total).toBe(0);
    expect(result.current.data?.status_counts?.all).toBe(1);
    expect(result.current.data?.status_counts?.completed).toBe(1);
    expect(result.current.data?.status_counts?.running).toBe(0);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("sorts and paginates demo analyses", async () => {
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useAnalyses(null, 2, 1, "all", "all", "", "date-asc"),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.page).toBe(2);
    expect(result.current.data?.per_page).toBe(1);
    expect(result.current.data?.total).toBeGreaterThan(1);
    expect(result.current.data?.items).toHaveLength(1);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("creates and reads a generated demo analysis without calling the API", async () => {
    const wrapper = createWrapper();
    const created = renderHook(() => useCreateAnalysis(null), { wrapper });

    const analysis = await created.result.current.mutateAsync({
      client_idempotency_key: "analysis-launch-demo-test-123",
      compound_input: "celecoxib",
      input_type: "name",
      submitted_identity_confirmed: true,
      submitted_identity_value: "celecoxib",
    });

    expect(analysis.compound_name).toBe("Celecoxib");
    expect(analysis.status).toBe("completed");

    const detail = renderHook(() => useAnalysis(analysis.id, null), {
      wrapper,
    });

    await waitFor(() => expect(detail.result.current.isSuccess).toBe(true));

    expect(detail.result.current.data?.compound_name).toBe("Celecoxib");
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
