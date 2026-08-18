import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));
vi.mock("@/lib/constants", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/constants")>("@/lib/constants");

  return {
    ...actual,
    DEMO_MODE_ENABLED: true,
    DEV_AUTH_BYPASS_ENABLED: true,
  };
});

import { apiClient } from "@/lib/api-client";
import {
  analysisReviewStatusKey,
  useAnalysisReviewStatus,
  useUpdateAnalysisReviewStatus,
} from "@/hooks/use-analysis-review-status";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  return { Wrapper, queryClient };
}

describe("useAnalysisReviewStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the review status by analysis id", async () => {
    const mockStatus = {
      analysis_id: "analysis-1",
      status: "under_review",
      note: "Initial legal review in progress",
      reviewer_name: "Ada Lovelace",
      reviewer_email: "ada@example.com",
      reviewed_at: "2026-04-18T10:30:00Z",
      updated_at: "2026-04-18T10:35:00Z",
      decision_counts: { accept: 4, reject: 1, edit: 2 },
      findings_total: 12,
      findings_reviewed: 7,
      completion_pct: 58.3333,
    };
    mockApiClient.mockResolvedValueOnce(mockStatus);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAnalysisReviewStatus("analysis-1"), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockStatus);
    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/analysis-1/review-status",
      expect.objectContaining({
        token: "test-token",
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("serves local demo review status without an API request", async () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useAnalysisReviewStatus("ana_demo_001"),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      analysis_id: "ana_demo_001",
      status: "under_review",
      findings_reviewed: 4,
      findings_total: 5,
      completion_pct: 80,
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("stays idle without an analysis id", () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAnalysisReviewStatus(""), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});

describe("useUpdateAnalysisReviewStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates the review status and invalidates review/status caches", async () => {
    mockApiClient.mockResolvedValueOnce({
      analysis_id: "analysis-1",
      status: "approved",
      note: "Ready for export",
      reviewer_name: "Ada Lovelace",
      reviewer_email: "ada@example.com",
      reviewed_at: "2026-04-18T11:00:00Z",
      updated_at: "2026-04-18T11:00:00Z",
      decision_counts: { accept: 5, reject: 1, edit: 2 },
      findings_total: 12,
      findings_reviewed: 12,
      completion_pct: 100,
    });

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(
      () => useUpdateAnalysisReviewStatus("analysis-1"),
      { wrapper: Wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({
        status: "approved",
        note: "Ready for export",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/analysis-1/review-status",
      expect.objectContaining({
        method: "PUT",
        token: "test-token",
      }),
    );

    const [, opts] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(opts.body))).toEqual({
      status: "approved",
      note: "Ready for export",
    });
    expect(
      queryClient.getQueryData(
        analysisReviewStatusKey("analysis-1", "test-token"),
      ),
    ).toMatchObject({
      status: "approved",
      note: "Ready for export",
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: analysisReviewStatusKey("analysis-1"),
        predicate: expect.any(Function),
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["analyses", "analysis-1"],
        predicate: expect.any(Function),
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["analyses"],
        predicate: expect.any(Function),
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["reports", "analysis-1"],
        predicate: expect.any(Function),
      }),
    );
  });

  it("omits note from the payload when not provided", async () => {
    mockApiClient.mockResolvedValueOnce({
      analysis_id: "analysis-1",
      status: "pending",
      note: null,
      reviewer_name: null,
      reviewer_email: null,
      reviewed_at: null,
      updated_at: "2026-04-18T11:00:00Z",
      decision_counts: { accept: 0, reject: 0, edit: 0 },
      findings_total: 0,
      findings_reviewed: 0,
      completion_pct: 0,
    });

    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useUpdateAnalysisReviewStatus("analysis-1"),
      { wrapper: Wrapper },
    );

    await act(async () => {
      await result.current.mutateAsync({ status: "pending" });
    });

    const [, opts] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(opts.body))).toEqual({
      status: "pending",
    });
  });
});
