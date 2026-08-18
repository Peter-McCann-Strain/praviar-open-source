import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockUseAuthToken = vi.fn();
const mockUseUser = vi.fn();
const mockUseComments = vi.fn();
const mockUseCreateComment = vi.fn();
const mockUseCommentReviewers = vi.fn();
const mockUseCommentAssignmentHistory = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: vi.fn(),
  isAuthBoundaryError: vi.fn(() => false),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@clerk/nextjs", () => ({
  useUser: () => mockUseUser(),
}));

vi.mock(import("@/hooks/use-comments"), async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-comments")>();

  return {
    ...actual,
    useComments: (...args: unknown[]) => mockUseComments(...args),
    useCreateComment: (...args: unknown[]) => mockUseCreateComment(...args),
    useCommentReviewers: (...args: unknown[]) =>
      mockUseCommentReviewers(...args),
    useCommentAssignmentHistory: (...args: unknown[]) =>
      mockUseCommentAssignmentHistory(...args),
  };
});

import { apiClient } from "@/lib/api-client";
import { CommentPanel } from "@/components/report/comment-panel";

const mockApiClient = vi.mocked(apiClient);

const comments = [
  {
    id: "c1",
    user_id: "user-alpha",
    body: "Top-level comment",
    target_type: "analysis",
    target_id: "analysis-1",
    parent_id: null,
    resolved: false,
    assigned_to: null,
    assigned_reviewer_name: null,
    assigned_reviewer_email: null,
    assigned_at: null,
    assignment_event_count: 0,
    last_assignment_at: null,
    queue_age_hours: 4,
    is_overdue: false,
    escalation_event_count: 0,
    last_escalation_at: null,
    escalation_status: null,
    created_at: "2026-04-12T09:50:00.000Z",
  },
];

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  return { queryClient, wrapper };
}

describe("CommentPanel review queue actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("dev-token");
    mockUseUser.mockReturnValue({
      isLoaded: true,
      user: {
        id: "reviewer-1",
        fullName: "Alice Attorney",
        primaryEmailAddress: { emailAddress: "alice@example.com" },
      },
    });
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
    });
    mockUseCreateComment.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
    mockUseCommentReviewers.mockReturnValue({
      data: [
        {
          id: "reviewer-1",
          label: "Alice Attorney",
          email: "alice@example.com",
          role: "attorney",
        },
        {
          id: "reviewer-2",
          label: "Ben Admin",
          email: "ben@example.com",
          role: "admin",
        },
      ],
      error: null,
    });
    mockUseCommentAssignmentHistory.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
  });

  it("invalidates review-queue queries after assigning a reviewer", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "c1",
      assigned_to: "reviewer-1",
      assigned_by: "reviewer-1",
      assigned_reviewer_name: "Alice Attorney",
      assigned_reviewer_email: "alice@example.com",
      assigned_at: new Date().toISOString(),
      assignment_event_count: 1,
      last_assignment_at: new Date().toISOString(),
      queue_age_hours: 4,
      is_overdue: false,
    });
    const { queryClient, wrapper } = createWrapper();
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");

    render(<CommentPanel analysisId="analysis-1" />, { wrapper });

    fireEvent.change(screen.getByLabelText("Assign owner"), {
      target: { value: "reviewer-1" },
    });

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["review-queue"],
          predicate: expect.any(Function),
        }),
      );
    });
    expect(screen.getByText(/Assigned to Alice Attorney/)).toBeInTheDocument();
  });

  it("keeps comment bodies intact and lets refreshed server data replace local action patches", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "c1",
      body: "",
      assigned_to: "reviewer-1",
      assigned_by: "reviewer-1",
      assigned_reviewer_name: "Alice Attorney",
      assigned_reviewer_email: "alice@example.com",
      assigned_at: new Date().toISOString(),
      assignment_event_count: 1,
      last_assignment_at: new Date().toISOString(),
    });
    const { wrapper } = createWrapper();

    const { rerender } = render(<CommentPanel analysisId="analysis-1" />, {
      wrapper,
    });

    fireEvent.change(screen.getByLabelText("Assign owner"), {
      target: { value: "reviewer-1" },
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Assigned to Alice Attorney/),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("Top-level comment")).toBeInTheDocument();

    mockUseComments.mockReturnValue({
      data: [
        {
          ...comments[0],
          body: "Server refreshed comment",
          assigned_to: "reviewer-2",
          assigned_reviewer_name: "Ben Admin",
          assigned_reviewer_email: "ben@example.com",
        },
      ],
      isLoading: false,
    });

    rerender(<CommentPanel analysisId="analysis-1" />);

    expect(screen.getByText("Server refreshed comment")).toBeInTheDocument();
    expect(screen.getByText(/Assigned to Ben Admin/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Assigned to Alice Attorney/),
    ).not.toBeInTheDocument();
  });

  it("invalidates review-queue queries after resolving a thread", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "c1",
      resolved: true,
      resolved_by: "reviewer-1",
      resolved_at: new Date().toISOString(),
    });
    const { wrapper } = createWrapper();

    render(<CommentPanel analysisId="analysis-1" />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      expect(
        screen.getByText("No open threads. Everything here is resolved."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "Resolve" }),
    ).not.toBeInTheDocument();
  });

  it("invalidates review-queue queries after escalating a thread", async () => {
    mockApiClient.mockResolvedValueOnce({
      id: "c1",
      escalated_at: new Date().toISOString(),
      escalated_by: "reviewer-1",
      escalated_by_name: "Alice Attorney",
      escalated_by_email: "alice@example.com",
      escalation_event_count: 1,
      last_escalation_at: new Date().toISOString(),
      escalation_status: "escalated",
      escalated_to_review: true,
      review_handoff_comment_id: "handoff-1",
    });
    const { queryClient, wrapper } = createWrapper();
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");

    render(<CommentPanel analysisId="analysis-1" />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith(
        expect.objectContaining({
          queryKey: ["review-queue"],
          predicate: expect.any(Function),
        }),
      );
    });
    expect(
      screen.getByText(/Escalated to legal review by Alice Attorney/),
    ).toBeInTheDocument();
  });
});
