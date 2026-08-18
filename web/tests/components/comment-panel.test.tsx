import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CommentPanel } from "@/components/report/comment-panel";
import type { CommentPanelComment } from "@/components/report/comment-panel-types";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";
import { APIError } from "@/lib/api-client";

const mockUseComments = vi.fn();
const mockUseCommentReviewers = vi.fn();
const mockUseCreateComment = vi.fn();
const mockUseAssignComment = vi.fn();
const mockUseToggleCommentResolution = vi.fn();
const mockUseEscalateComment = vi.fn();
const mockFocus = vi.fn();
const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
const focusSpy = vi
  .spyOn(HTMLElement.prototype, "focus")
  .mockImplementation(() => mockFocus());

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "dev-token",
}));

vi.mock("@/hooks/use-comments", () => ({
  useComments: (...args: unknown[]) => mockUseComments(...args),
  useCommentReviewers: (...args: unknown[]) => mockUseCommentReviewers(...args),
  useCreateComment: (...args: unknown[]) => mockUseCreateComment(...args),
  useAssignComment: (...args: unknown[]) => mockUseAssignComment(...args),
  useToggleCommentResolution: (...args: unknown[]) =>
    mockUseToggleCommentResolution(...args),
  useEscalateComment: (...args: unknown[]) => mockUseEscalateComment(...args),
  useCommentAssignmentHistory: () => ({
    data: null,
    isLoading: false,
    error: null,
  }),
}));

const comments: CommentPanelComment[] = [
  {
    id: "c1",
    user_id: "user-alpha",
    body: "Top-level comment",
    target_type: "analysis",
    target_id: "analysis-1",
    parent_id: null,
    resolved: true,
    created_at: "2026-04-12T09:50:00.000Z",
  },
  {
    id: "c2",
    user_id: "user-beta",
    body: "Reply comment",
    target_type: "analysis",
    target_id: "analysis-1",
    parent_id: "c1",
    resolved: false,
    created_at: "2026-04-12T10:00:00.000Z",
  },
];

describe("CommentPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseComments.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCommentReviewers.mockReturnValue({
      data: [],
    });
    mockUseCreateComment.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "c-new" }),
      isPending: false,
    });
    mockUseAssignComment.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "c1" }),
      isPending: false,
    });
    mockUseToggleCommentResolution.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "c1" }),
      isPending: false,
    });
    mockUseEscalateComment.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ id: "c1" }),
      isPending: false,
    });
  });

  afterAll(() => {
    consoleErrorSpy.mockRestore();
    focusSpy.mockRestore();
  });

  it("renders the empty state when there are no comments", () => {
    render(<CommentPanel analysisId="analysis-1" />);

    expect(screen.getByText("Discussion")).toBeInTheDocument();
    expect(
      screen.getByText("No comments yet. Start the discussion."),
    ).toBeInTheDocument();
  });

  it("renders a threaded conversation and focuses the composer when replying", () => {
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Top-level comment")).toBeInTheDocument();
    expect(screen.getByText("Reply comment")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reply" }));

    expect(screen.getByText("Replying to comment")).toBeInTheDocument();
    expect(mockFocus).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText("Replying to comment")).not.toBeInTheDocument();
  });

  it("submits via ctrl+enter and clears reply state after success", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: "c-new" });
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
    });
    mockUseCreateComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Reply" }));

    const textarea = screen.getByPlaceholderText(
      "Add a comment about this analysis...",
    );
    fireEvent.change(textarea, { target: { value: "  Needs more detail  " } });
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-1",
        body: "Needs more detail",
        parent_id: "c1",
        target_type: "analysis",
        target_id: "analysis-1",
      });
    });

    expect(screen.queryByText("Replying to comment")).not.toBeInTheDocument();
    expect(textarea).toHaveValue("");
  });

  it("preserves a draft and refreshes discussion before any repost when the post outcome is unknown", async () => {
    const refetch = vi.fn().mockResolvedValue({ error: null });
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(
        new Error("postgres://secret-token comment backend exploded"),
      );
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch,
    });
    mockUseCreateComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Reply" }));
    const textarea = screen.getByPlaceholderText(
      "Add a comment about this analysis...",
    );
    fireEvent.change(textarea, { target: { value: "Needs counsel review" } });
    const commentButton = screen.getByRole("button", { name: "Comment" });
    expect(commentButton).toHaveClass("min-h-11");
    fireEvent.click(commentButton);

    await waitFor(() => {
      expect(screen.getByTestId("comment-post-recovery")).toHaveAttribute(
        "data-mutation-recovery-mode",
        "outcome-unknown",
      );
    });

    expect(textarea).toHaveValue("Needs counsel review");
    expect(textarea).toBeDisabled();
    expect(screen.getByText("Replying to comment")).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("comment-post-recovery-action"));

    await waitFor(() => {
      expect(refetch).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByTestId("comment-post-recovery"),
      ).not.toBeInTheDocument();
    });
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(textarea).toHaveValue("Needs counsel review");
    expect(screen.getByText("Replying to comment")).toBeInTheDocument();
  });

  it("preserves a definitively failed post for review without reposting it", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new APIError(422, "postgres://secret invalid"));
    mockUseCreateComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    const textarea = screen.getByPlaceholderText(
      "Add a comment about this analysis...",
    );
    fireEvent.change(textarea, { target: { value: "Needs counsel review" } });
    fireEvent.click(screen.getByRole("button", { name: "Comment" }));

    await waitFor(() => {
      expect(screen.getByTestId("comment-post-recovery")).toHaveAttribute(
        "data-mutation-recovery-mode",
        "failed",
      );
    });
    fireEvent.click(screen.getByText("Review draft"));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(textarea).toHaveValue("Needs counsel review");
    expect(
      screen.queryByTestId("comment-post-recovery"),
    ).not.toBeInTheDocument();
  });

  it("retries the exact assignment inline while sibling thread mutations stay locked", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce(new Error("assignment outcome unknown"))
      .mockResolvedValueOnce({
        id: "c1",
        assigned_to: "reviewer-1",
      });
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseCommentReviewers.mockReturnValue({
      data: [
        {
          id: "reviewer-1",
          email: "reviewer@example.com",
          full_name: "Reviewer One",
          label: "Reviewer One (reviewer@example.com)",
          role: "attorney",
        },
      ],
    });
    mockUseAssignComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    const assignmentControls = screen.getAllByRole("combobox", {
      name: "Assign owner",
    });
    fireEvent.change(assignmentControls[0], {
      target: { value: "reviewer-1" },
    });

    await waitFor(() => {
      expect(
        screen.getByTestId("comment-assignment-recovery-c1"),
      ).toHaveAttribute("data-mutation-recovery-mode", "outcome-unknown");
    });
    expect(assignmentControls[1]).toBeDisabled();
    expect(
      screen.getAllByRole("button", { name: /Resolve|Unresolve/ })[1],
    ).toBeDisabled();

    fireEvent.click(
      screen.getByTestId("comment-assignment-recovery-c1-action"),
    );

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync).toHaveBeenNthCalledWith(1, {
      analysis_id: "analysis-1",
      comment_id: "c1",
      assigned_to: "reviewer-1",
    });
    expect(mutateAsync).toHaveBeenNthCalledWith(2, {
      analysis_id: "analysis-1",
      comment_id: "c1",
      assigned_to: "reviewer-1",
    });
    expect(
      screen.queryByTestId("comment-assignment-recovery-c1"),
    ).not.toBeInTheDocument();
  });

  it("serializes thread mutations so concurrent actions cannot overwrite recovery", async () => {
    let resolveMutation:
      | ((value: { id: string; resolved: boolean }) => void)
      | null = null;
    const resolveMutateAsync = vi.fn(
      () =>
        new Promise<{ id: string; resolved: boolean }>((resolve) => {
          resolveMutation = resolve;
        }),
    );
    const escalateMutateAsync = vi.fn().mockResolvedValue({ id: "c2" });
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseToggleCommentResolution.mockReturnValue({
      mutateAsync: resolveMutateAsync,
      isPending: false,
    });
    mockUseEscalateComment.mockReturnValue({
      mutateAsync: escalateMutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Unresolve" }));

    await waitFor(() => {
      for (const button of screen.getAllByRole("button", {
        name: "Escalate",
      })) {
        expect(button).toBeDisabled();
      }
      for (const select of screen.getAllByRole("combobox", {
        name: "Assign owner",
      })) {
        expect(select).toBeDisabled();
      }
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Escalate" })[1]);
    expect(escalateMutateAsync).not.toHaveBeenCalled();

    await act(async () => {
      resolveMutation?.({ id: "c1", resolved: false });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "Escalate" })[1],
      ).toBeEnabled();
    });
  });

  it("refreshes an unknown resolution outcome without rewriting resolution state", async () => {
    const refetch = vi.fn().mockResolvedValue({ error: null });
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce(new Error("resolution outcome unknown"));
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch,
    });
    mockUseToggleCommentResolution.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Unresolve" }));

    await waitFor(() => {
      expect(
        screen.getByTestId("comment-resolution-recovery-c1"),
      ).toHaveAttribute("data-mutation-recovery-mode", "outcome-unknown");
    });
    fireEvent.click(
      screen.getByTestId("comment-resolution-recovery-c1-action"),
    );

    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByTestId("comment-resolution-recovery-c1"),
    ).not.toBeInTheDocument();
  });

  it("lets a reviewer dismiss a definitive resolution failure and revise safely", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce(new APIError(422, "cannot update"));
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseToggleCommentResolution.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Unresolve" }));

    await waitFor(() => {
      expect(
        screen.getByTestId("comment-resolution-recovery-c1"),
      ).toHaveAttribute("data-mutation-recovery-mode", "failed");
    });
    fireEvent.click(
      screen.getByTestId("comment-resolution-recovery-c1-dismiss"),
    );

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByTestId("comment-resolution-recovery-c1"),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: /Resolve|Unresolve/ })[1],
    ).toBeEnabled();
  });

  it("refreshes an unknown escalation outcome without submitting a second escalation", async () => {
    const refetch = vi.fn().mockResolvedValue({ error: null });
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new Error("escalation outcome unknown"));
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch,
    });
    mockUseEscalateComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getAllByRole("button", { name: "Escalate" })[0]);

    await waitFor(() => {
      expect(
        screen.getByTestId("comment-escalation-recovery-c1"),
      ).toHaveAttribute("data-mutation-recovery-mode", "outcome-unknown");
    });
    fireEvent.click(
      screen.getByTestId("comment-escalation-recovery-c1-action"),
    );

    await waitFor(() => {
      expect(refetch).toHaveBeenCalledTimes(1);
      expect(
        screen.queryByTestId("comment-escalation-recovery-c1"),
      ).not.toBeInTheDocument();
    });
    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  it("reveals the focused submit action below the sticky report command rail", async () => {
    const commandBar = document.createElement("div");
    commandBar.setAttribute("data-praviar-mobile-command-bar", "");
    commandBar.getBoundingClientRect = vi.fn(
      () => ({ bottom: 158, top: 100 }) as DOMRect,
    );
    document.body.appendChild(commandBar);
    const scrollBy = vi
      .spyOn(window, "scrollBy")
      .mockImplementation(() => undefined);

    try {
      render(<CommentPanel analysisId="analysis-1" />);
      fireEvent.change(
        screen.getByPlaceholderText("Add a comment about this analysis..."),
        { target: { value: "Needs review" } },
      );
      const commentButton = screen.getByRole("button", { name: "Comment" });
      commentButton.getBoundingClientRect = vi.fn(
        () => ({ bottom: 189, top: 145 }) as DOMRect,
      );

      fireEvent.focus(commentButton);

      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({
          top: -25,
          behavior: "auto",
        }),
      );
      expect(commentButton).toHaveClass("scroll-mt-[11.5rem]");
    } finally {
      scrollBy.mockRestore();
      commandBar.remove();
    }
  });

  it("shows the loading state while comments are loading", () => {
    mockUseComments.mockReturnValue({
      data: [],
      isLoading: true,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    expect(screen.getByText("Discussion")).toBeInTheDocument();
    expect(
      screen.queryByText("No comments yet. Start the discussion."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Loading comments" }),
    ).toBeInTheDocument();
  });

  it("renders a recovery state instead of a false empty discussion on comment load errors", () => {
    const refetch = vi.fn();
    mockUseComments.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("postgres://secret comments failed"),
      refetch,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    expect(
      screen.getByText("Comments temporarily unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("comment-panel-load-error")).toHaveAttribute(
      "role",
      "alert",
    );
    expect(
      screen.queryByText("No comments yet. Start the discussion."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Add a comment about this analysis..."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry comments load" }),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("hides cached comments and composer when comment access is revoked", () => {
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });

    render(<CommentPanel analysisId="analysis-1" />);

    expect(screen.getByText("Comment access restricted")).toBeInTheDocument();
    expect(screen.queryByText("Top-level comment")).not.toBeInTheDocument();
    expect(screen.queryByText("Reply comment")).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Add a comment about this analysis..."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reply" }),
    ).not.toBeInTheDocument();
  });

  it("clears private draft and reply state on auth boundary changes", () => {
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Reply" }));
    const textarea = screen.getByPlaceholderText(
      "Add a comment about this analysis...",
    );
    fireEvent.change(textarea, { target: { value: "private counsel draft" } });

    expect(screen.getByText("Replying to comment")).toBeInTheDocument();
    expect(textarea).toHaveValue("private counsel draft");

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(screen.queryByText("Replying to comment")).not.toBeInTheDocument();
    expect(textarea).toHaveValue("");
  });

  it("releases an in-flight recovery lock on auth boundary changes", async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new Error("comment outcome unknown"));
    const refetch = vi.fn(() => new Promise(() => undefined));
    mockUseComments.mockReturnValue({
      data: comments,
      isLoading: false,
      error: null,
      refetch,
    });
    mockUseCreateComment.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    render(<CommentPanel analysisId="analysis-1" />);

    const textarea = screen.getByPlaceholderText(
      "Add a comment about this analysis...",
    );
    fireEvent.change(textarea, { target: { value: "private recovery draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Comment" }));

    await waitFor(() =>
      expect(screen.getByTestId("comment-post-recovery")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("comment-post-recovery-action"));
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    expect(textarea).toBeDisabled();

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(
      screen.queryByTestId("comment-post-recovery"),
    ).not.toBeInTheDocument();
    expect(textarea).toBeEnabled();
    expect(textarea).toHaveValue("");
  });
});
