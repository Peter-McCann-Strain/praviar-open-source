import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
}));

const mockApiClient = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: mockApiClient,
  };
});

import {
  resetDemoCommentsState,
  useComments,
  useCreateComment,
} from "@/hooks/use-comments";
import { useReviewQueue } from "@/hooks/use-review-queue";
import { resetDemoReviewQueueState } from "@/lib/demo-review-queue";

const ANALYSIS_ID = "ana_demo_001";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("demo comment creation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetDemoCommentsState();
    resetDemoReviewQueueState();
  });

  it("persists root comments and replies locally without an API request", async () => {
    const { result } = renderHook(
      () => ({
        comments: useComments(ANALYSIS_ID, null),
        create: useCreateComment(null),
        queue: useReviewQueue(null, "unassigned"),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.comments.data).toHaveLength(2));
    await waitFor(() => expect(result.current.queue.isSuccess).toBe(true));

    let rootCommentId = "";
    await act(async () => {
      const created = await result.current.create.mutateAsync({
        analysis_id: ANALYSIS_ID,
        body: "Counsel should review the new claim mapping.",
        target_type: "analysis",
        target_id: ANALYSIS_ID,
      });
      rootCommentId = created.id;
    });

    await waitFor(() => expect(result.current.comments.data).toHaveLength(3));
    expect(result.current.comments.data).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: rootCommentId,
          body: "Counsel should review the new claim mapping.",
          parent_id: null,
          user_id: "user-demo-ada",
        }),
      ]),
    );
    await waitFor(() =>
      expect(result.current.queue.data).toMatchObject({
        counts: { total: 4, unassigned: 2 },
      }),
    );
    expect(
      result.current.queue.data && "items" in result.current.queue.data
        ? result.current.queue.data.items.find(
            (item) => item.id === rootCommentId,
          )
        : undefined,
    ).toMatchObject({
      comment_body: "Counsel should review the new claim mapping.",
      comment_count: 1,
    });

    await act(async () => {
      await result.current.create.mutateAsync({
        analysis_id: ANALYSIS_ID,
        body: "Reply captured in the local demo thread.",
        parent_id: rootCommentId,
        target_type: "analysis",
        target_id: ANALYSIS_ID,
      });
    });

    await waitFor(() => expect(result.current.comments.data).toHaveLength(4));
    await waitFor(() => {
      const queueItem =
        result.current.queue.data && "items" in result.current.queue.data
          ? result.current.queue.data.items.find(
              (item) => item.id === rootCommentId,
            )
          : undefined;
      expect(queueItem).toMatchObject({ comment_count: 2 });
    });
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
