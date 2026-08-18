import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({ apiClient: vi.fn() }));
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

import { apiClient } from "@/lib/api-client";
import { useReviewHandoff } from "@/hooks/use-review-handoff";

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

describe("useReviewHandoff", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("posts the governed handoff payload and invalidates related caches", async () => {
    mockApiClient.mockResolvedValueOnce({
      comment_id: "comment-1",
      review_status: {
        analysis_id: "analysis-1",
        status: "under_review",
        note: "Escalated from governed evidence handoff.",
        reviewer_name: "Ada Lovelace",
        reviewer_email: "ada@example.com",
        reviewed_at: "2026-04-18T10:30:00Z",
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 0,
        findings_reviewed: 0,
        completion_pct: 0,
      },
      escalated_to_review: true,
      target_type: "analysis",
      target_id: "analysis-1",
    });

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useReviewHandoff("analysis-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        body: "Review this claim support",
        target_type: "claim",
        target_id: "claim-1",
      });
    });

    expect(mockApiClient).toHaveBeenCalledWith(
      "/analyses/analysis-1/review-handoff",
      expect.objectContaining({
        method: "POST",
        token: "test-token",
      }),
    );

    const [, options] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(options?.body))).toEqual({
      body: "Review this claim support",
      target_type: "claim",
      target_id: "claim-1",
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["comments", "analysis-1"],
        predicate: expect.any(Function),
      }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ["analyses", "analysis-1", "review-status"],
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
        queryKey: ["reports", "analysis-1"],
        predicate: expect.any(Function),
      }),
    );
  });

  it("surfaces the returned handoff response", async () => {
    mockApiClient.mockResolvedValueOnce({
      comment_id: "comment-99",
      review_status: {
        analysis_id: "analysis-1",
        status: "approved",
        note: "Approved for export.",
        reviewer_name: "Ada Lovelace",
        reviewer_email: "ada@example.com",
        reviewed_at: "2026-04-18T10:30:00Z",
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 0,
        findings_reviewed: 0,
        completion_pct: 0,
      },
      escalated_to_review: true,
      target_type: "patent",
      target_id: "US123",
    });

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useReviewHandoff("analysis-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        body: "Escalate this item",
        target_type: "patent",
        target_id: "US123",
      });
    });

    await waitFor(() => {
      expect(result.current.data?.comment_id).toBe("comment-99");
      expect(result.current.data?.review_status.status).toBe("approved");
    });
  });

  it("preserves analysis-level review notes and promotion intent", async () => {
    mockApiClient.mockResolvedValueOnce({
      comment_id: "comment-analysis",
      review_status: {
        analysis_id: "analysis-1",
        status: "under_review",
        note: "Reliance handoff from report readiness console.",
        reviewer_name: "Ada Lovelace",
        reviewer_email: "ada@example.com",
        reviewed_at: "2026-04-18T10:30:00Z",
        updated_at: "2026-04-18T10:30:00Z",
        decision_counts: { accept: 0, reject: 0, edit: 0 },
        findings_total: 4,
        findings_reviewed: 2,
        completion_pct: 50,
      },
      escalated_to_review: true,
      target_type: "analysis",
      target_id: "analysis-1",
    });

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useReviewHandoff("analysis-1"), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        body: "Report: PRV-2026-0142\nBlocking jurisdictions: US, EP",
        promote_to_under_review: true,
        review_note: "Reliance handoff from report readiness console.",
        target_id: "analysis-1",
        target_type: "analysis",
      });
    });

    const [, options] = mockApiClient.mock.calls[0];
    expect(JSON.parse(String(options?.body))).toEqual({
      body: "Report: PRV-2026-0142\nBlocking jurisdictions: US, EP",
      promote_to_under_review: true,
      review_note: "Reliance handoff from report readiness console.",
      target_id: "analysis-1",
      target_type: "analysis",
    });
  });
});
