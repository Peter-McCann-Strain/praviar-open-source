import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseToggleCommentResolution = vi.fn();
const mockUseEscalateComment = vi.fn();
const mockUseAssignComment = vi.fn();
const mockUseCommentReviewers = vi.fn();

vi.mock("@/hooks/use-comments", () => ({
  useAssignComment: (...args: unknown[]) => mockUseAssignComment(...args),
  useCommentReviewers: (...args: unknown[]) => mockUseCommentReviewers(...args),
  useToggleCommentResolution: (...args: unknown[]) =>
    mockUseToggleCommentResolution(...args),
  useEscalateComment: (...args: unknown[]) => mockUseEscalateComment(...args),
}));

const principalState = vi.hoisted(() => ({
  canAssign: true,
  canResolve: true,
  canEscalate: true,
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_assign_review: principalState.canAssign,
      can_resolve_review: principalState.canResolve,
      can_escalate_review: principalState.canEscalate,
    },
  }),
}));

import { ReviewQueueBulkToolbar } from "@/components/reviews/review-queue-bulk-toolbar";

describe("ReviewQueueBulkToolbar", () => {
  const onClearSelection = vi.fn();
  const onActionComplete = vi.fn();
  const assignMutateAsync = vi.fn();
  const resolveMutateAsync = vi.fn();
  const escalateMutateAsync = vi.fn();

  const selectedItems = [
    {
      id: "comment-1",
      analysis_id: "analysis-1",
      compound_name: "Aspirin",
      analysis_status: "completed",
      overall_risk: "high",
      comment_body: "Blocking claim needs review.",
      assigned_to_id: "user-1",
      assigned_to_name: "Ada Lovelace",
      assigned_to_email: "ada@example.com",
      is_mine: true,
      is_unassigned: false,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      escalated_at: null,
      queue_age_hours: 12,
      last_activity_at: "2026-04-18T10:30:00Z",
      updated_at: "2026-04-18T10:30:00Z",
      comment_count: 2,
    },
    {
      id: "comment-2",
      analysis_id: "analysis-1",
      compound_name: "Ibuprofen",
      analysis_status: "completed",
      overall_risk: "medium",
      comment_body: "Needs legal handoff.",
      assigned_to_id: null,
      assigned_to_name: null,
      assigned_to_email: null,
      is_mine: false,
      is_unassigned: true,
      is_overdue: true,
      overdue_label: "Overdue · 2d open",
      is_escalated: false,
      escalated_at: null,
      queue_age_hours: 52,
      last_activity_at: "2026-04-18T09:10:00Z",
      updated_at: "2026-04-18T09:10:00Z",
      comment_count: 1,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    principalState.canAssign = true;
    principalState.canResolve = true;
    principalState.canEscalate = true;
    onClearSelection.mockReset();
    onClearSelection.mockResolvedValue(undefined);
    onActionComplete.mockReset();
    assignMutateAsync.mockResolvedValue({ id: "comment-1" });
    resolveMutateAsync.mockResolvedValue({ id: "comment-1" });
    escalateMutateAsync.mockResolvedValue({ id: "comment-1" });
    mockUseAssignComment.mockReturnValue({
      mutateAsync: assignMutateAsync,
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
          label: "Bob Reviewer",
          email: "bob@example.com",
          role: "attorney",
        },
      ],
      isLoading: false,
    });
    mockUseToggleCommentResolution.mockReturnValue({
      mutateAsync: resolveMutateAsync,
      isPending: false,
    });
    mockUseEscalateComment.mockReturnValue({
      mutateAsync: escalateMutateAsync,
      isPending: false,
    });
  });

  function confirmBulkAction(name: RegExp | string) {
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name }));
  }

  it("renders the selected bulk triage summary", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    expect(screen.getByTestId("review-queue-bulk-toolbar")).toBeInTheDocument();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(screen.getByText("Aspirin, Ibuprofen")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Resolve selected/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Escalate selected/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Assign selected/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toBeInTheDocument();
  });

  it("uses touch-safe mobile bulk controls", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    expect(screen.getByLabelText("Bulk assign owner")).toHaveClass(
      "h-11",
      "w-full",
    );
    expect(screen.getByLabelText("Bulk assign owner")).not.toHaveClass(
      "sm:h-9",
    );
    expect(
      screen.getByRole("button", { name: /Assign selected/i }),
    ).toHaveClass("min-h-11", "w-full");
    expect(
      screen.getByRole("button", { name: /Resolve selected/i }),
    ).toHaveClass("min-h-11", "w-full");
    expect(
      screen.getByRole("button", { name: /Escalate selected/i }),
    ).toHaveClass("min-h-11", "w-full");
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toHaveClass("min-h-11", "w-full");
  });

  it("disables bulk controls when the parent queue is locked", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
        actionsDisabled
      />,
    );

    expect(screen.getByLabelText("Bulk assign owner")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Assign selected/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Resolve selected/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Escalate selected/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toBeDisabled();
  });

  it("keeps clear selection disabled while a bulk mutation is pending", async () => {
    resolveMutateAsync.mockImplementation(() => new Promise(() => {}));
    const nonUrgentItems = [
      {
        ...selectedItems[0],
        overall_risk: "medium",
        is_overdue: false,
        overdue_label: null,
        is_escalated: false,
      },
    ];

    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={nonUrgentItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve selected/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Clear selection/i }),
      ).toBeDisabled();
    });
    expect(
      screen.getByRole("button", { name: /Resolve selected/i }),
    ).toBeDisabled();
    expect(onClearSelection).not.toHaveBeenCalled();
  });

  it("renders compact mode with shortened bulk-action copy", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        mode="compact"
      />,
    );

    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(
      screen.getByText("Resolve, escalate, or reassign selected threads."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Owner assignment is ready across this shared scope."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assign" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Escalate" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("renders compact mode labels and copy", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        mode="compact"
      />,
    );

    expect(
      screen.getByRole("button", { name: /^Assign$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Resolve$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Escalate$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Clear$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/resolve, escalate, or reassign selected threads\./i),
    ).toBeInTheDocument();
  });

  it("bulk assigns selected items when the selection shares one analysis scope", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "reviewer-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Assign selected/i }));
    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(assignMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-1",
      assigned_to: "reviewer-2",
    });
    expect(assignMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-2",
      assigned_to: "reviewer-2",
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "assign",
      count: 2,
      scopeLabel: "Aspirin",
      sharedAnalysisId: "analysis-1",
      assignedToLabel: "Bob Reviewer",
    });
    expect(onClearSelection).toHaveBeenCalled();
  });

  it("confirms assignment against captured target items after selectedItems rerender", async () => {
    const { rerender } = render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "reviewer-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Assign selected/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    rerender(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          {
            ...selectedItems[0],
            id: "comment-new",
            analysis_id: "analysis-new",
            compound_name: "New visible selection",
          },
        ]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(assignMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-1",
      assigned_to: "reviewer-2",
    });
    expect(assignMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-2",
      assigned_to: "reviewer-2",
    });
    expect(assignMutateAsync).not.toHaveBeenCalledWith(
      expect.objectContaining({ comment_id: "comment-new" }),
    );
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "assign",
      count: 2,
      scopeLabel: "Aspirin",
      sharedAnalysisId: "analysis-1",
      assignedToLabel: "Bob Reviewer",
    });
  });

  it("requires an explicit reviewer before bulk assignment", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    const assignButton = screen.getByRole("button", {
      name: /Assign selected/i,
    });
    expect(assignButton).toBeDisabled();

    fireEvent.click(assignButton);

    expect(assignMutateAsync).not.toHaveBeenCalled();
    expect(onActionComplete).not.toHaveBeenCalled();
  });

  it("bulk clears owner assignment for a shared-scope selection", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "__clear_owner__" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Clear owners/i }));
    expect(screen.getByText(/Owner will be cleared/i)).toBeInTheDocument();
    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(assignMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-1",
      assigned_to: null,
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "assign",
      count: 1,
      skippedCount: 1,
      scopeLabel: "Aspirin",
      sharedAnalysisId: "analysis-1",
      assignedToLabel: "Unassigned",
    });
    expect(onClearSelection).toHaveBeenCalled();
  });

  it("keeps owner clearing available when reviewer options are unavailable", async () => {
    mockUseCommentReviewers.mockReturnValueOnce({
      data: [],
      isLoading: false,
    });

    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[selectedItems[0]]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "__clear_owner__" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Clear owners/i }));
    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-1",
        comment_id: "comment-1",
        assigned_to: null,
      });
    });
  });

  it("allows owner clearing across mixed analysis selections", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          selectedItems[0],
          {
            ...selectedItems[1],
            analysis_id: "analysis-2",
          },
        ]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "__clear_owner__" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Clear owners/i }));
    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "assign",
      count: 1,
      skippedCount: 1,
      scopeLabel: "Aspirin",
      sharedAnalysisId: "analysis-1",
      assignedToLabel: "Unassigned",
    });
  });

  it("lets reviewers cancel a guarded bulk action without changing thread state", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve selected/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(resolveMutateAsync).not.toHaveBeenCalled();
    expect(onClearSelection).not.toHaveBeenCalled();
    expect(onActionComplete).not.toHaveBeenCalled();
  });

  it("disables reviewer assignment but keeps owner clearing when reviewer options are unavailable", () => {
    mockUseCommentReviewers.mockReturnValueOnce({
      data: [],
      isLoading: false,
    });

    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
      />,
    );

    expect(screen.getByLabelText("Bulk assign owner")).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /Assign selected/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("option", { name: /Clear owner/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/unavailable until the reviewer list loads/i),
    ).toBeInTheDocument();
  });

  it("bulk resolves selected items and clears selection on success", async () => {
    const longCompoundName = `N-(4-hydroxyphenyl)-${"bulk-review-thread-".repeat(6)}`;
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          { ...selectedItems[0], compound_name: longCompoundName },
          selectedItems[1],
        ]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve selected/i }));
    expect(screen.getByText(longCompoundName)).toHaveAttribute(
      "title",
      longCompoundName,
    );
    expect(screen.getByText(longCompoundName)).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getAllByText(/analysis-1/u).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("button", { name: "Confirm resolution" }),
    ).toHaveClass("min-h-11");
    confirmBulkAction(/Confirm resolution/i);

    await waitFor(() => {
      expect(resolveMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(resolveMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-1",
      resolved: true,
    });
    expect(resolveMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-2",
      resolved: true,
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "resolve",
      count: 2,
      scopeLabel: longCompoundName,
      sharedAnalysisId: "analysis-1",
    });
    expect(onClearSelection).toHaveBeenCalled();
  });

  it("bulk resolves mixed-scope selections without borrowing the first compound scope", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          selectedItems[0],
          {
            ...selectedItems[1],
            analysis_id: "analysis-2",
          },
        ]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve selected/i }));
    confirmBulkAction(/Confirm resolution/i);

    await waitFor(() => {
      expect(resolveMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "resolve",
      count: 2,
      scopeLabel: null,
      sharedAnalysisId: null,
    });
  });

  it("bulk escalates selected items and clears selection on success", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Escalate selected/i }));
    confirmBulkAction(/Confirm escalation/i);

    await waitFor(() => {
      expect(escalateMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(escalateMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-1",
      promote_to_under_review: true,
    });
    expect(escalateMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-2",
      promote_to_under_review: true,
    });
    expect(onClearSelection).toHaveBeenCalled();
  });

  it("skips already-escalated items and reports the actual escalated target", async () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          {
            ...selectedItems[0],
            is_escalated: true,
            escalated_at: "2026-04-18T10:45:00Z",
          },
          selectedItems[1],
        ]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Escalate selected/i }));
    confirmBulkAction(/Confirm escalation/i);

    await waitFor(() => {
      expect(escalateMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(escalateMutateAsync).toHaveBeenCalledWith({
      analysis_id: "analysis-1",
      comment_id: "comment-2",
      promote_to_under_review: true,
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "escalate",
      count: 1,
      scopeLabel: "Ibuprofen",
      sharedAnalysisId: "analysis-1",
    });
  });

  it("disables bulk escalation when every selected thread is already escalated", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems.map((item) => ({
          ...item,
          is_escalated: true,
          escalated_at: "2026-04-18T10:45:00Z",
        }))}
        onClearSelection={onClearSelection}
      />,
    );

    const escalateButton = screen.getByRole("button", {
      name: /Escalate selected/i,
    });
    expect(escalateButton).toBeDisabled();

    fireEvent.click(escalateButton);
    expect(escalateMutateAsync).not.toHaveBeenCalled();
  });

  it("reports partial bulk failures without exposing backend diagnostics", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    resolveMutateAsync
      .mockRejectedValueOnce(new Error("postgres://secret resolve failed"))
      .mockResolvedValueOnce({ id: "comment-2" });

    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve selected/i }));
    confirmBulkAction(/Confirm resolution/i);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /1 of 2 selected thread resolutions were not saved/i,
      );
    });
    expect(
      screen.getByText(/1 of 2 selected thread resolutions were not saved/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "resolve",
      count: 1,
      scopeLabel: "Ibuprofen",
      sharedAnalysisId: "analysis-1",
    });
    expect(onClearSelection).not.toHaveBeenCalled();

    consoleError.mockRestore();
  });

  it("reports partial assignment failures using captured target count", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    assignMutateAsync
      .mockRejectedValueOnce(new Error("postgres://secret assign failed"))
      .mockResolvedValueOnce({ id: "comment-2" });
    const { rerender } = render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );

    fireEvent.change(screen.getByLabelText("Bulk assign owner"), {
      target: { value: "reviewer-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Assign selected/i }));

    rerender(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[selectedItems[0]]}
        onClearSelection={onClearSelection}
        onActionComplete={onActionComplete}
      />,
    );
    confirmBulkAction(/Confirm assignment/i);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /1 of 2 selected owner changes were not saved/i,
      );
    });
    expect(onActionComplete).toHaveBeenCalledWith({
      action: "assign",
      count: 1,
      scopeLabel: "Ibuprofen",
      sharedAnalysisId: "analysis-1",
      assignedToLabel: "Bob Reviewer",
    });
    expect(onClearSelection).not.toHaveBeenCalled();

    consoleError.mockRestore();
  });

  it("hides itself with no selected items", () => {
    const { container } = render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[]}
        onClearSelection={onClearSelection}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("disables mixed-scope reviewer assignment while keeping owner clearing available", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          selectedItems[0],
          {
            ...selectedItems[1],
            analysis_id: "analysis-2",
          },
        ]}
        onClearSelection={onClearSelection}
      />,
    );

    expect(screen.getByLabelText("Bulk assign owner")).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /Assign selected/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("option", { name: /Clear owner/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/limited to selections from a single analysis scope/i),
    ).toBeInTheDocument();
  });

  it("keeps compact mode explicit when owner assignment is not ready", () => {
    render(
      <ReviewQueueBulkToolbar
        token="tok"
        selectedItems={[
          selectedItems[0],
          {
            ...selectedItems[1],
            analysis_id: "analysis-2",
          },
        ]}
        onClearSelection={onClearSelection}
        mode="compact"
      />,
    );

    expect(
      screen.getByText(
        "Owner assignment only works within one analysis scope.",
      ),
    ).toBeInTheDocument();
  });
});
