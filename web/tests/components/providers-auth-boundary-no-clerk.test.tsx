import React, { useEffect } from "react";
import { act, render, waitFor } from "@testing-library/react";
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/use-clerk-session", () => ({
  hasClerk: false,
}));

import { Providers } from "@/app/providers";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useReviewStore } from "@/stores/review-store";

function QueryClientProbe({
  onClient,
}: {
  onClient: (client: QueryClient) => void;
}) {
  const queryClient = useQueryClient();

  useEffect(() => {
    onClient(queryClient);
  }, [onClient, queryClient]);

  return null;
}

describe("Providers auth boundary cache hygiene without Clerk", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePipelineStore.getState().reset();
    useReviewStore.getState().resetAll();
  });

  it("purges private queries, mutations, and stores on explicit auth boundary events", async () => {
    let queryClient: QueryClient | null = null;

    render(
      <Providers>
        <QueryClientProbe
          onClient={(client) => {
            queryClient = client;
          }}
        />
      </Providers>,
    );

    await waitFor(() => expect(queryClient).not.toBeNull());
    queryClient!.setQueryData(["reports", "analysis-1", "scope-a"], {
      report_id: "private-report",
    });
    queryClient!.setQueryData(["public-reference-data"], {
      version: "2026-06",
    });
    queryClient!.getMutationCache().build(queryClient!, {
      mutationKey: ["billing", "checkout", "scope-a"],
      mutationFn: async () => ({ ok: true }),
    });
    usePipelineStore.getState().setError("private pipeline error");
    useReviewStore
      .getState()
      .overrideRisk(
        "analysis-1",
        "US123",
        "high",
        "private reviewer note",
        "user-1",
      );

    expect(
      queryClient!.getQueryData(["reports", "analysis-1", "scope-a"]),
    ).toEqual({
      report_id: "private-report",
    });
    expect(queryClient!.getMutationCache().getAll()).toHaveLength(1);
    expect(usePipelineStore.getState().error).toBe("private pipeline error");
    expect(
      useReviewStore.getState().getReview("analysis-1", "US123")?.notes,
    ).toBe("private reviewer note");

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    await waitFor(() =>
      expect(queryClient!.getQueryCache().findAll()).toHaveLength(1),
    );
    expect(
      queryClient!.getQueryData(["reports", "analysis-1", "scope-a"]),
    ).toBeUndefined();
    expect(queryClient!.getQueryData(["public-reference-data"])).toEqual({
      version: "2026-06",
    });
    expect(queryClient!.getMutationCache().getAll()).toHaveLength(0);
    expect(usePipelineStore.getState().error).toBeNull();
    expect(useReviewStore.getState().getAnalysisReviews("analysis-1")).toEqual(
      {},
    );
  });
});
