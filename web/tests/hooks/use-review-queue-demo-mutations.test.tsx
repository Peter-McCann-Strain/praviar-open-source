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
  useAssignComment,
  useEscalateComment,
  useToggleCommentResolution,
} from "@/hooks/use-comments";
import { useReviewQueue } from "@/hooks/use-review-queue";
import { resetDemoReviewQueueState } from "@/lib/demo-review-queue";

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

describe("demo review queue mutations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetDemoReviewQueueState();
  });

  it("clears a demo owner into the unassigned slice without calling the API", async () => {
    const { result } = renderHook(
      () => ({
        mine: useReviewQueue(null, "mine"),
        unassigned: useReviewQueue(null, "unassigned"),
        assign: useAssignComment(null),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.mine.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.unassigned.isSuccess).toBe(true));
    expect(result.current.mine.data).toMatchObject({
      counts: { mine: 1, unassigned: 1 },
    });

    await act(async () => {
      await result.current.assign.mutateAsync({
        analysis_id: "ana_demo_003",
        comment_id: "rq-demo-1",
        assigned_to: null,
      });
    });

    await waitFor(() => {
      expect(result.current.mine.data).toMatchObject({
        counts: { mine: 0, unassigned: 2 },
      });
    });
    expect(result.current.unassigned.data).toMatchObject({
      counts: { mine: 0, unassigned: 2 },
    });
    expect(
      result.current.unassigned.data &&
        "items" in result.current.unassigned.data
        ? result.current.unassigned.data.items.map((item) => item.id)
        : [],
    ).toContain("rq-demo-1");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("removes resolved demo rows from all open queue counts", async () => {
    const { result } = renderHook(
      () => ({
        overdue: useReviewQueue(null, "overdue"),
        escalated: useReviewQueue(null, "escalated"),
        resolve: useToggleCommentResolution(null),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.overdue.isSuccess).toBe(true));
    expect(result.current.overdue.data).toMatchObject({
      counts: { total: 3, overdue: 1, escalated: 2 },
    });

    await act(async () => {
      await result.current.resolve.mutateAsync({
        analysis_id: "ana_demo_001",
        comment_id: "rq-demo-3",
        resolved: true,
      });
    });

    await waitFor(() => {
      expect(result.current.overdue.data).toMatchObject({
        counts: { total: 2, overdue: 0, escalated: 1 },
      });
    });
    const escalatedIds =
      result.current.escalated.data && "items" in result.current.escalated.data
        ? result.current.escalated.data.items.map((item) => item.id)
        : [];
    expect(escalatedIds).not.toContain("rq-demo-3");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("persists demo escalation exactly once", async () => {
    const { result } = renderHook(
      () => ({
        escalated: useReviewQueue(null, "escalated"),
        escalate: useEscalateComment(null),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.escalated.isSuccess).toBe(true));
    expect(result.current.escalated.data).toMatchObject({
      counts: { escalated: 2 },
    });

    await act(async () => {
      await result.current.escalate.mutateAsync({
        analysis_id: "ana_demo_002",
        comment_id: "rq-demo-2",
      });
      await result.current.escalate.mutateAsync({
        analysis_id: "ana_demo_002",
        comment_id: "rq-demo-2",
      });
    });

    await waitFor(() => {
      expect(result.current.escalated.data).toMatchObject({
        counts: { total: 3, escalated: 3 },
      });
    });
    const escalatedIds =
      result.current.escalated.data && "items" in result.current.escalated.data
        ? result.current.escalated.data.items.map((item) => item.id)
        : [];
    expect(escalatedIds.filter((id) => id === "rq-demo-2")).toHaveLength(1);
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("does not resurrect resolved demo rows when stale UI escalates them", async () => {
    const { result } = renderHook(
      () => ({
        unassigned: useReviewQueue(null, "unassigned"),
        escalated: useReviewQueue(null, "escalated"),
        resolve: useToggleCommentResolution(null),
        escalate: useEscalateComment(null),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.unassigned.isSuccess).toBe(true));

    await act(async () => {
      await result.current.resolve.mutateAsync({
        analysis_id: "ana_demo_002",
        comment_id: "rq-demo-2",
        resolved: true,
      });
      await result.current.escalate.mutateAsync({
        analysis_id: "ana_demo_002",
        comment_id: "rq-demo-2",
      });
    });

    await waitFor(() => {
      expect(result.current.unassigned.data).toMatchObject({
        counts: { total: 2, unassigned: 0, escalated: 2 },
      });
    });
    const escalatedIds =
      result.current.escalated.data && "items" in result.current.escalated.data
        ? result.current.escalated.data.items.map((item) => item.id)
        : [];
    expect(escalatedIds).not.toContain("rq-demo-2");
    expect(mockApiClient).not.toHaveBeenCalled();
  });
});
