import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: false,
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    apiClient: vi.fn(),
  };
});

import { APIError, apiClient } from "@/lib/api-client";
import { useReviewQueue } from "@/hooks/use-review-queue";

const mockApiClient = vi.mocked(apiClient);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

function createWrapperWithClient(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

function jwt(claims: Record<string, unknown>) {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `header.${payload}.signature`;
}

function queueResponse(label: string) {
  return {
    counts: {
      open_total: 1,
      mine: 1,
      assigned: 1,
      unassigned: 0,
      overdue: 0,
      escalated: 0,
    },
    items: [
      {
        id: `${label}-rq-1`,
        analysis_id: `${label}-ana-1`,
        compound_name: `${label} compound`,
        analysis_status: "completed",
        overall_risk: "medium",
        body: `${label} queue item`,
        assigned_to: "user-1",
        assigned_reviewer_name: "Ada Lovelace",
        assigned_reviewer_email: "ada@example.com",
        queue_age_hours: 4,
        is_overdue: false,
        escalation_event_count: 0,
        escalated_at: null,
        last_assignment_at: "2026-04-18T08:00:00Z",
        last_escalation_at: null,
        created_at: "2026-04-18T08:00:00Z",
      },
    ],
  };
}

describe("useReviewQueue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is disabled when the token is missing", () => {
    const { result } = renderHook(() => useReviewQueue(null, "mine"), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiClient).not.toHaveBeenCalled();
  });

  it("fetches the queue for the selected filter", async () => {
    mockApiClient.mockResolvedValueOnce({
      counts: {
        open_total: 1,
        mine: 1,
        assigned: 1,
        unassigned: 0,
        overdue: 0,
        escalated: 0,
      },
      items: [],
    });

    const { result } = renderHook(() => useReviewQueue("tok", "mine"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiClient).toHaveBeenCalledWith(
      "/comments/review-queue?filter=mine",
      expect.objectContaining({ token: "tok" }),
    );
  });

  it("does not reuse cached queue data across auth boundary changes", async () => {
    const adminToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:admin",
    });
    const memberToken = jwt({
      sub: "user_1",
      org_id: "org_1",
      sid: "sess_1",
      org_role: "org:member",
    });
    mockApiClient
      .mockResolvedValueOnce(queueResponse("admin"))
      .mockResolvedValueOnce(queueResponse("member"));
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = createWrapperWithClient(queryClient);

    const { result: adminResult } = renderHook(
      () => useReviewQueue(adminToken, "mine"),
      { wrapper },
    );
    await waitFor(() => expect(adminResult.current.isSuccess).toBe(true));

    const { result: memberResult } = renderHook(
      () => useReviewQueue(memberToken, "mine"),
      { wrapper },
    );
    await waitFor(() => expect(memberResult.current.isSuccess).toBe(true));

    expect(adminResult.current.data).toMatchObject({
      items: [{ id: "admin-rq-1" }],
    });
    expect(memberResult.current.data).toMatchObject({
      items: [{ id: "member-rq-1" }],
    });
    expect(mockApiClient).toHaveBeenCalledTimes(2);
  });

  it("preserves queue aging details when mapping queue items", async () => {
    mockApiClient.mockResolvedValueOnce({
      counts: {
        open_total: 1,
        mine: 1,
        assigned: 1,
        unassigned: 0,
        overdue: 1,
        escalated: 0,
      },
      items: [
        {
          id: "rq-1",
          analysis_id: "ana-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          body: "Owned thread approaching a deadline.",
          assigned_to: "user-1",
          assigned_reviewer_name: "Ada Lovelace",
          assigned_reviewer_email: "ada@example.com",
          queue_age_hours: 52,
          is_overdue: true,
          escalation_event_count: 0,
          escalated_at: null,
          last_assignment_at: "2026-04-18T08:00:00Z",
          last_escalation_at: null,
          created_at: "2026-04-17T04:00:00Z",
        },
      ],
    });

    const { result } = renderHook(() => useReviewQueue("tok", "mine"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      counts: {
        total: 1,
        mine: 1,
        overdue: 1,
      },
      items: [
        {
          id: "rq-1",
          queue_age_hours: 52,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          assigned_to_name: "Ada Lovelace",
        },
      ],
    });
  });

  it("uses the newest mapped queue activity for updated_at instead of the first item", async () => {
    mockApiClient.mockResolvedValueOnce({
      counts: {
        open_total: 2,
        mine: 2,
        assigned: 2,
        unassigned: 0,
        overdue: 1,
        escalated: 0,
      },
      items: [
        {
          id: "rq-old-priority",
          analysis_id: "ana-1",
          compound_name: "Old urgent item",
          analysis_status: "completed",
          overall_risk: "high",
          body: "Old item sorted first by priority.",
          assigned_to: "user-1",
          assigned_reviewer_name: "Ada Lovelace",
          assigned_reviewer_email: "ada@example.com",
          queue_age_hours: 52,
          is_overdue: true,
          escalation_event_count: 0,
          escalated_at: null,
          last_assignment_at: "2026-04-17T08:00:00Z",
          last_escalation_at: null,
          created_at: "2026-04-17T08:00:00Z",
        },
        {
          id: "rq-newer",
          analysis_id: "ana-2",
          compound_name: "Newer activity item",
          analysis_status: "completed",
          overall_risk: "medium",
          body: "Newer item appears later in the API response.",
          assigned_to: "user-2",
          assigned_reviewer_name: "Grace Hopper",
          assigned_reviewer_email: "grace@example.com",
          queue_age_hours: 6,
          is_overdue: false,
          escalation_event_count: 0,
          escalated_at: null,
          last_assignment_at: "2026-04-18T12:30:00Z",
          last_escalation_at: null,
          created_at: "2026-04-18T12:30:00Z",
        },
      ],
    });

    const { result } = renderHook(() => useReviewQueue("tok", "mine"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      updated_at: "2026-04-18T12:30:00Z",
    });
  });

  it("uses the newest assignment timestamp when it happens after escalation", async () => {
    mockApiClient.mockResolvedValueOnce({
      counts: {
        open_total: 1,
        mine: 1,
        assigned: 1,
        unassigned: 0,
        overdue: 0,
        escalated: 1,
      },
      items: [
        {
          id: "rq-reassigned",
          analysis_id: "ana-reassigned",
          compound_name: "Reassigned escalation",
          analysis_status: "completed",
          overall_risk: "high",
          body: "Escalated yesterday and reassigned today.",
          assigned_to: "user-2",
          assigned_reviewer_name: "Grace Hopper",
          assigned_reviewer_email: "grace@example.com",
          queue_age_hours: 24,
          is_overdue: false,
          escalation_event_count: 1,
          escalated_at: "2026-04-17T08:00:00Z",
          last_escalation_at: "2026-04-17T08:00:00Z",
          last_assignment_at: "2026-04-18T13:00:00Z",
          created_at: "2026-04-16T08:00:00Z",
        },
      ],
    });

    const { result } = renderHook(() => useReviewQueue("tok", "escalated"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toMatchObject({
      updated_at: "2026-04-18T13:00:00Z",
      items: [
        {
          id: "rq-reassigned",
          last_activity_at: "2026-04-18T13:00:00Z",
          updated_at: "2026-04-18T13:00:00Z",
        },
      ],
    });
  });

  it("converts 403 responses into a quiet forbidden sentinel", async () => {
    mockApiClient.mockRejectedValueOnce(new APIError(403, "Forbidden"));

    const { result } = renderHook(() => useReviewQueue("tok", "overdue"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({ forbidden: true });
    expect(result.current.isError).toBe(false);
  });

  it("converts 401 responses into a quiet forbidden sentinel", async () => {
    mockApiClient.mockRejectedValueOnce(
      new APIError(401, "Authentication required"),
    );

    const { result } = renderHook(() => useReviewQueue("tok", "overdue"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual({ forbidden: true });
    expect(result.current.isError).toBe(false);
  });
});
