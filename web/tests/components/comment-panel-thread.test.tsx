import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommentPanelThread } from "@/components/report/comment-panel-thread";
import type { CommentPanelComment } from "@/components/report/comment-panel-types";
import { COMMENT_ASSIGNMENT_ACTIVITY_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";

const mockUseCommentAssignmentHistory = vi.fn();

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "dev-token",
}));

vi.mock("@/hooks/use-comments", () => ({
  useCommentAssignmentHistory: (...args: unknown[]) =>
    mockUseCommentAssignmentHistory(...args),
}));

const comment: CommentPanelComment = {
  id: "c1",
  user_id: "user-alpha",
  body: "Top-level comment",
  target_type: "review_handoff",
  target_id: "analysis-1",
  parent_id: null,
  resolved: true,
  resolved_by: "attorney-1",
  resolved_at: new Date(Date.now() - 15_000).toISOString(),
  assigned_to: "reviewer-1",
  assigned_by: "attorney-2",
  assigned_reviewer_name: "Alice Attorney",
  assigned_reviewer_email: "alice@example.com",
  assigned_at: new Date(Date.now() - 45_000).toISOString(),
  assignment_event_count: 3,
  last_assignment_at: new Date(Date.now() - 45_000).toISOString(),
  queue_age_hours: 48,
  is_overdue: false,
  created_at: "2026-04-12T09:50:00.000Z",
};

const reply: CommentPanelComment = {
  id: "c2",
  user_id: "user-beta",
  body: "Reply comment",
  target_type: "review_handoff",
  target_id: "analysis-1",
  parent_id: "c1",
  resolved: false,
  created_at: "2026-04-12T10:00:00.000Z",
};

const reviewerOptions = [
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
];

describe("CommentPanelThread", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCommentAssignmentHistory.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
  });

  it("surfaces handoff target metadata on the thread and replies", () => {
    const onReply = vi.fn();
    const onToggleResolved = vi.fn();

    render(
      <CommentPanelThread
        comment={comment}
        replies={[reply]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={3}
        threadLastAssignedAt={new Date(Date.now() - 45_000).toISOString()}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={onReply}
        onAssignReviewer={vi.fn()}
        onToggleResolved={onToggleResolved}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.getAllByText("Review handoff target")).toHaveLength(2);
    expect(screen.getAllByText("Current analysis")).toHaveLength(2);
    expect(screen.queryByText("analysis-1")).not.toBeInTheDocument();
    expect(
      screen.getByText("Resolved by Counsel reviewer · just now"),
    ).toBeInTheDocument();
    expect(screen.getByText("Thread open")).toBeInTheDocument();
    expect(screen.getByText("Opened 2d ago")).toBeInTheDocument();
    expect(screen.getByText(/3 assignments/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Unresolve" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resolve" })).toHaveClass(
      "min-h-11",
    );

    const replyButton = screen.getByRole("button", { name: "Reply" });
    expect(replyButton).toHaveClass(
      "opacity-100",
      "sm:focus-visible:opacity-100",
      "min-h-11",
    );
    expect(replyButton).not.toHaveClass("opacity-0");

    fireEvent.click(replyButton);

    expect(onReply).toHaveBeenCalledWith("c1");
  });

  it("wraps long comment bodies and target IDs", () => {
    render(
      <CommentPanelThread
        comment={{
          ...comment,
          body: "A".repeat(180),
          target_id: "target-" + "B".repeat(140),
        }}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.getByText("A".repeat(180))).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Current analysis")).toBeInTheDocument();
    expect(
      screen.queryByText("target-" + "B".repeat(140)),
    ).not.toBeInTheDocument();
  });

  it("omits the metadata strip when the target fields are blank", () => {
    const onReply = vi.fn();

    render(
      <CommentPanelThread
        comment={{
          ...comment,
          target_type: "",
          target_id: "",
        }}
        replies={[]}
        threadStatus="resolved"
        threadResolvedAt={comment.resolved_at ?? null}
        threadResolvedBy={comment.resolved_by ?? null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={onReply}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.queryByText("Review handoff target")).not.toBeInTheDocument();
    expect(screen.getByText("Top-level comment")).toBeInTheDocument();
  });

  it("disables the resolve action and shows inline errors while pending", () => {
    const onReply = vi.fn();
    const onToggleResolved = vi.fn();

    render(
      <CommentPanelThread
        comment={comment}
        replies={[]}
        threadStatus="resolved"
        threadResolvedAt={comment.resolved_at ?? null}
        threadResolvedBy={comment.resolved_by ?? null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={onReply}
        onAssignReviewer={vi.fn()}
        onToggleResolved={onToggleResolved}
        isResolutionPending={true}
        pendingCommentId="c1"
        resolutionError={{ commentId: "c1", message: "Resolution failed." }}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    const action = screen.getByRole("button", { name: "Unresolving..." });
    expect(action).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Resolution failed.");

    fireEvent.click(action);

    expect(onToggleResolved).not.toHaveBeenCalled();
  });

  it("surfaces thread-level resolution timing for resolved threads", () => {
    const onReply = vi.fn();

    render(
      <CommentPanelThread
        comment={{
          ...comment,
          resolved: false,
          resolved_by: null,
          resolved_at: null,
        }}
        replies={[
          {
            ...reply,
            resolved: true,
            resolved_by: null,
            resolved_at: null,
          },
        ]}
        threadStatus="resolved"
        threadResolvedAt={new Date(Date.now() - 10_000).toISOString()}
        threadResolvedBy="attorney-2"
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={onReply}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.getByText("Thread resolved")).toBeInTheDocument();
    expect(
      screen.getByText("Resolved by Counsel reviewer · just now"),
    ).toBeInTheDocument();
  });

  it("supports reviewer assignment from the thread picker", () => {
    const onAssignReviewer = vi.fn();

    render(
      <CommentPanelThread
        comment={{
          ...comment,
          resolved: false,
          resolved_by: null,
          resolved_at: null,
          assigned_to: null,
          assigned_reviewer_name: null,
          assigned_reviewer_email: null,
          assigned_at: null,
          assignment_event_count: 0,
          last_assignment_at: null,
          queue_age_hours: 24,
          is_overdue: false,
        }}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={onAssignReviewer}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    const assignOwner = screen.getByLabelText("Assign owner");
    expect(assignOwner).toHaveClass("min-h-11");
    fireEvent.change(assignOwner, {
      target: { value: "reviewer-1" },
    });

    expect(onAssignReviewer).toHaveBeenCalledWith("c1", "reviewer-1");
    expect(screen.getAllByLabelText("Assign owner")).toHaveLength(1);
  });

  it("surfaces escalation metadata on overdue threads", () => {
    const onReply = vi.fn();

    render(
      <CommentPanelThread
        comment={{
          ...comment,
          resolved: false,
          resolved_by: null,
          resolved_at: null,
          escalated_at: new Date(Date.now() - 40_000).toISOString(),
          escalated_by: "attorney-1",
          escalated_by_name: "Alice Attorney",
          escalated_by_email: "alice@example.com",
          escalation_event_count: 2,
          last_escalation_at: new Date(Date.now() - 40_000).toISOString(),
          escalation_status: "escalated",
          queue_age_hours: 72,
          is_overdue: true,
        }}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadEscalatedAt={new Date(Date.now() - 40_000).toISOString()}
        threadEscalatedBy="attorney-1"
        threadEscalatedByName="Alice Attorney"
        threadEscalatedByEmail="alice@example.com"
        threadEscalationEventCount={2}
        threadLastEscalatedAt={new Date(Date.now() - 40_000).toISOString()}
        threadIsEscalated={true}
        threadEscalatedToReview={true}
        threadReviewHandoffCommentId="handoff-1234"
        threadAgeLabel="Open 3d"
        threadOverdueLabel="Overdue · 3d open"
        threadIsOverdue={true}
        onReply={onReply}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.getByText("Legal review")).toBeInTheDocument();
    expect(
      screen.getByText("2 escalations · Last escalated just now"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Review handoff comment handoff-/),
    ).toBeInTheDocument();
    expect(screen.getByText("Overdue · 3d open")).toBeInTheDocument();
    expect(screen.getByText("Open 3d")).toBeInTheDocument();
  });

  it("exposes a top-level escalate action", () => {
    const onEscalateComment = vi.fn();

    render(
      <CommentPanelThread
        comment={{
          ...comment,
          resolved: false,
          resolved_by: null,
          resolved_at: null,
          escalated_at: null,
          escalated_by: null,
          escalated_by_name: null,
          escalated_by_email: null,
          escalation_event_count: 0,
          last_escalation_at: null,
          escalation_status: "none",
        }}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadEscalatedAt={null}
        threadEscalatedBy={null}
        threadEscalatedByName={null}
        threadEscalatedByEmail={null}
        threadEscalationEventCount={0}
        threadLastEscalatedAt={null}
        threadIsEscalated={false}
        threadAgeLabel="Open 2d"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onEscalateComment={onEscalateComment}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Escalate" }));

    expect(onEscalateComment).toHaveBeenCalledWith("c1");
  });

  it("shows a per-comment escalating state and disables only that escalate action", () => {
    render(
      <CommentPanelThread
        comment={{
          ...comment,
          resolved: false,
          resolved_by: null,
          resolved_at: null,
          escalated_at: null,
          escalated_by: null,
          escalation_event_count: 0,
          escalation_status: "none",
        }}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadIsEscalated={false}
        threadAgeLabel="Open 2d"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onEscalateComment={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        isEscalationPending={true}
        pendingEscalateCommentId="c1"
        reviewerOptions={reviewerOptions}
      />,
    );

    const escalating = screen.getByRole("button", { name: "Escalating..." });
    expect(escalating).toBeDisabled();
    // Resolve and assign remain interactive — escalation pending is scoped to
    // the escalate control of the matching comment only.
    expect(screen.getByRole("button", { name: "Resolve" })).not.toBeDisabled();
    expect(screen.getByLabelText("Assign owner")).not.toBeDisabled();
  });

  it("marks resolved threads with a distinct status indicator", () => {
    render(
      <CommentPanelThread
        comment={comment}
        replies={[]}
        threadStatus="resolved"
        threadResolvedAt={comment.resolved_at ?? null}
        threadResolvedBy={comment.resolved_by ?? null}
        threadAssignedReviewerId={null}
        threadAssignedReviewerName={null}
        threadAssignedReviewerEmail={null}
        threadAssignedAt={null}
        threadAssignmentHistoryCount={0}
        threadLastAssignedAt={null}
        threadAgeLabel="Opened 2d ago"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    const label = screen.getByText("Thread resolved");
    expect(label).toHaveClass("text-success");
  });

  it("reveals assignment activity when expanded", () => {
    mockUseCommentAssignmentHistory.mockReturnValue({
      data: {
        comment_id: "c1",
        thread_root_comment_id: "c1",
        analysis_id: "analysis-1",
        assignment_event_count: 2,
        last_assignment_at: new Date(Date.now() - 10_000).toISOString(),
        events: [
          {
            id: "evt-1",
            comment_id: "c1",
            analysis_id: "analysis-1",
            event_type: "assigned",
            assigned_to: "reviewer-1",
            assigned_to_name: "Alice Attorney",
            assigned_to_email: "alice@example.com",
            assigned_by: "scientist-1",
            assigned_by_name: "Sam Scientist",
            assigned_by_email: "sam@example.com",
            created_at: new Date(Date.now() - 10_000).toISOString(),
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(
      <CommentPanelThread
        comment={comment}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={comment.assigned_to ?? null}
        threadAssignedReviewerName={comment.assigned_reviewer_name ?? null}
        threadAssignedReviewerEmail={comment.assigned_reviewer_email ?? null}
        threadAssignedAt={comment.assigned_at ?? null}
        threadAssignmentHistoryCount={3}
        threadLastAssignedAt={comment.last_assignment_at ?? null}
        threadAgeLabel="Open 2d"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(mockUseCommentAssignmentHistory).toHaveBeenCalledWith(
      "c1",
      "dev-token",
      false,
    );

    fireEvent.click(screen.getByRole("button", { name: "View activity" }));

    expect(screen.getByText("Assignment activity")).toBeInTheDocument();
    expect(
      screen.getByText("Assigned to Alice Attorney by Sam Scientist"),
    ).toBeInTheDocument();
  });

  it("shows loading and error states for assignment activity", () => {
    mockUseCommentAssignmentHistory.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    const { rerender } = render(
      <CommentPanelThread
        comment={comment}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={comment.assigned_to ?? null}
        threadAssignedReviewerName={comment.assigned_reviewer_name ?? null}
        threadAssignedReviewerEmail={comment.assigned_reviewer_email ?? null}
        threadAssignedAt={comment.assigned_at ?? null}
        threadAssignmentHistoryCount={3}
        threadLastAssignedAt={comment.last_assignment_at ?? null}
        threadAgeLabel="Open 2d"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "View activity" }));
    expect(
      screen.getByText("Loading assignment activity..."),
    ).toBeInTheDocument();

    mockUseCommentAssignmentHistory.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("postgres://secret-token history failed"),
    });

    rerender(
      <CommentPanelThread
        comment={comment}
        replies={[]}
        threadStatus="open"
        threadResolvedAt={null}
        threadResolvedBy={null}
        threadAssignedReviewerId={comment.assigned_to ?? null}
        threadAssignedReviewerName={comment.assigned_reviewer_name ?? null}
        threadAssignedReviewerEmail={comment.assigned_reviewer_email ?? null}
        threadAssignedAt={comment.assigned_at ?? null}
        threadAssignmentHistoryCount={3}
        threadLastAssignedAt={comment.last_assignment_at ?? null}
        threadAgeLabel="Open 2d"
        threadOverdueLabel={null}
        threadIsOverdue={false}
        onReply={vi.fn()}
        onAssignReviewer={vi.fn()}
        onToggleResolved={vi.fn()}
        isResolutionPending={false}
        pendingCommentId={null}
        resolutionError={null}
        isAssignmentPending={false}
        pendingAssignmentCommentId={null}
        assignmentError={null}
        reviewerOptions={reviewerOptions}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      COMMENT_ASSIGNMENT_ACTIVITY_ERROR_MESSAGE,
    );
    expect(
      screen.queryByText(/postgres:\/\/secret-token/),
    ).not.toBeInTheDocument();
  });
});
