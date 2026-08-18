import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseCommentReviewers = vi.fn();
const mockUseAssignComment = vi.fn();
const mockUseToggleCommentResolution = vi.fn();
const mockUseEscalateComment = vi.fn();

vi.mock("@/hooks/use-comments", () => ({
  useCommentReviewers: (...args: unknown[]) => mockUseCommentReviewers(...args),
  useAssignComment: (...args: unknown[]) => mockUseAssignComment(...args),
  useToggleCommentResolution: (...args: unknown[]) =>
    mockUseToggleCommentResolution(...args),
  useEscalateComment: (...args: unknown[]) => mockUseEscalateComment(...args),
}));

const principalState = vi.hoisted(() => ({
  canAssign: true,
  canResolve: true,
  canEscalate: true,
  role: "attorney",
  riskRatingsRestricted: false,
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_assign_review: principalState.canAssign,
      can_resolve_review: principalState.canResolve,
      can_escalate_review: principalState.canEscalate,
      role: principalState.role,
      risk_ratings_restricted: principalState.riskRatingsRestricted,
    },
  }),
}));

import { ReviewQueueItemCard } from "@/components/reviews/review-queue-item-card";
import {
  buildReviewQueueItemHref,
  getReviewQueueItemActionLabel,
} from "@/components/reviews/review-queue-routing";

describe("ReviewQueueItemCard", () => {
  const onQueueRefresh = vi.fn();
  const assignMutateAsync = vi.fn();
  const resolveMutateAsync = vi.fn();
  const escalateMutateAsync = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    principalState.canAssign = true;
    principalState.canResolve = true;
    principalState.canEscalate = true;
    principalState.role = "attorney";
    principalState.riskRatingsRestricted = false;
    onQueueRefresh.mockResolvedValue(undefined);
    assignMutateAsync.mockResolvedValue({ id: "comment-1" });
    resolveMutateAsync.mockResolvedValue({ id: "comment-1", resolved: true });
    escalateMutateAsync.mockResolvedValue({ id: "comment-1" });

    mockUseCommentReviewers.mockReturnValue({
      data: [
        {
          id: "user-2",
          label: "Ada Lovelace",
          email: "ada@example.com",
          role: "attorney",
        },
      ],
      error: null,
      isLoading: false,
    });
    mockUseAssignComment.mockReturnValue({
      mutateAsync: assignMutateAsync,
      isPending: false,
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

  it.each([
    {
      role: "scientist",
      riskRatingsRestricted: true,
      label: "Open summary",
      href: "/analyses/analysis-policy/report/summary",
    },
    {
      role: "scientist",
      riskRatingsRestricted: false,
      label: "Open report",
      href: "/analyses/analysis-policy/report",
    },
    {
      role: "client",
      riskRatingsRestricted: false,
      label: "Open summary",
      href: "/analyses/analysis-policy/report/summary",
    },
    {
      role: "attorney",
      riskRatingsRestricted: true,
      label: "Open report",
      href: "/analyses/analysis-policy/report",
    },
  ])(
    "routes $role completed review work to the authorized report surface",
    ({ role, riskRatingsRestricted, label, href }) => {
      const item = {
        analysis_id: "analysis-policy",
        analysis_status: "completed",
      };

      expect(buildReviewQueueItemHref(item, role, riskRatingsRestricted)).toBe(
        href,
      );
      expect(
        getReviewQueueItemActionLabel(item, role, riskRatingsRestricted),
      ).toBe(label);
    },
  );

  it("keeps scientist actions inside assignment and escalation authority", () => {
    principalState.canResolve = false;

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-scientist",
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: null,
          comment_body: "Chemical interpretation needs counsel review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Resolve thread/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Counsel resolves")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Escalate/i })).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /Assign owner/i }),
    ).toBeDisabled();
  });

  it("renders the compact queue surface and opens the report", () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-1",
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Blocking claim needs review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 2,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.getByText(/Current owner/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Resolve thread/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Escalate/i }),
    ).toBeInTheDocument();
    const reportLink = screen.getByRole("link", { name: /Open report/i });
    expect(reportLink).toHaveAttribute("href", "/analyses/analysis-1/report");
    expect(reportLink).toHaveClass("w-full", "sm:w-auto");
  });

  it("routes running review items to the analysis run instead of a missing report", () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-running",
          analysis_id: "analysis-running",
          compound_name: "Ibuprofen",
          analysis_status: "running",
          overall_risk: null,
          comment_body: "Pending formulation question needs triage.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: false,
          is_unassigned: true,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    const runLink = screen.getByRole("link", { name: /View run/i });
    expect(runLink).toHaveAttribute("href", "/analyses/analysis-running");
    expect(
      screen.queryByRole("link", { name: /Open report/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps escalated high-risk threads visually urgent even when overdue", () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-urgent",
          analysis_id: "analysis-urgent",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Escalated blocker needs counsel review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: false,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 5d open",
          is_escalated: true,
          escalated_at: "2026-04-18T10:30:00Z",
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    const rail = screen.getByTestId("review-queue-priority-rail");
    expect(rail).toHaveClass("bg-error");
    expect(rail).not.toHaveClass("bg-warning");
    expect(screen.getAllByText("Escalated").length).toBeGreaterThan(0);
    expect(screen.getByText("Overdue · 5d open")).toBeInTheDocument();
  });

  it("uses mobile-stacked owner controls and item actions", () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-1",
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Blocking claim needs review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 2,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    expect(screen.getByLabelText(/Assign owner for Aspirin/i)).toHaveClass(
      "h-11",
      "w-full",
    );
    expect(screen.getByLabelText(/Assign owner for Aspirin/i)).not.toHaveClass(
      "sm:h-9",
    );
    expect(screen.getByRole("button", { name: /Assign owner/i })).toHaveClass(
      "min-h-11",
      "w-full",
    );
    expect(screen.getByRole("button", { name: /Resolve thread/i })).toHaveClass(
      "min-h-11",
      "w-full",
    );
    expect(screen.getByRole("button", { name: /Escalate/i })).toHaveClass(
      "min-h-11",
      "w-full",
    );
  });

  it("disables reviewer actions when the parent queue is locked", () => {
    const item = {
      id: "comment-1",
      analysis_id: "analysis-1",
      compound_name: "Aspirin",
      analysis_status: "completed",
      overall_risk: "high",
      comment_body: "Blocking claim needs review.",
      assigned_to_id: "user-1",
      assigned_to_name: "Alice Attorney",
      assigned_to_email: "alice@example.com",
      is_mine: true,
      is_unassigned: false,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      escalated_at: null,
      last_activity_at: "2026-04-18T10:30:00Z",
      updated_at: "2026-04-18T10:30:00Z",
      comment_count: 2,
    };

    const { rerender } = render(
      <ReviewQueueItemCard
        item={item}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Assign owner for Aspirin/i), {
      target: { value: "user-2" },
    });
    expect(screen.getByRole("button", { name: /Assign owner/i })).toBeEnabled();

    rerender(
      <ReviewQueueItemCard
        item={item}
        token="tok"
        onQueueRefresh={onQueueRefresh}
        actionsDisabled
      />,
    );

    expect(screen.getByLabelText(/Assign owner for Aspirin/i)).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Assign owner/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Resolve thread/i }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Escalate/i })).toBeDisabled();
  });

  it("assigns a reviewer and resolves the thread from the queue", async () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-1",
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Blocking claim needs review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 2,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Assign owner for Aspirin/i), {
      target: { value: "user-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Assign owner/i }));

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-1",
        comment_id: "comment-1",
        assigned_to: "user-2",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: /Resolve thread/i }));
    expect(resolveMutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText("Confirm thread resolution")).toBeInTheDocument();
    expect(screen.getByText(/High-risk thread/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Overdue · 2d open/i).length).toBeGreaterThan(1);
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm resolution/i }),
    );

    await waitFor(() => {
      expect(resolveMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-1",
        comment_id: "comment-1",
        resolved: true,
      });
    });

    expect(onQueueRefresh).toHaveBeenCalled();
  });

  it("keeps owner clearing available when reviewer options are unavailable", async () => {
    mockUseCommentReviewers.mockReturnValueOnce({
      data: [],
      error: new Error("postgres://secret reviewer list failed"),
      isLoading: false,
    });

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-owned",
          analysis_id: "analysis-owned",
          compound_name: "Imatinib",
          analysis_status: "completed",
          overall_risk: "medium",
          comment_body:
            "Owner should be clearable even without reviewer options.",
          assigned_to_id: "user-1",
          assigned_to_name: "Alice Attorney",
          assigned_to_email: "alice@example.com",
          is_mine: true,
          is_unassigned: false,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    const ownerSelect = screen.getByLabelText(/Assign owner for Imatinib/i);
    expect(ownerSelect).toBeEnabled();
    expect(screen.getAllByText("Alice Attorney").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/owner clearing remains available/i),
    ).toBeInTheDocument();

    fireEvent.change(ownerSelect, {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Clear owner/i }));

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-owned",
        comment_id: "comment-owned",
        assigned_to: null,
      });
    });
  });

  it("shows an owner as unassigned after clearing succeeds even when refresh fails", async () => {
    onQueueRefresh.mockRejectedValueOnce(new Error("refresh unavailable"));

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-owned",
          analysis_id: "analysis-owned",
          compound_name: "Imatinib",
          analysis_status: "completed",
          overall_risk: "medium",
          comment_body: "Owner should clear even if the queue refresh fails.",
          assigned_to_id: "user-1",
          assigned_to_name: "Alice Attorney",
          assigned_to_email: "alice@example.com",
          is_mine: true,
          is_unassigned: false,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Assign owner for Imatinib/i), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Clear owner/i }));

    await waitFor(() => {
      expect(assignMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-owned",
        comment_id: "comment-owned",
        assigned_to: null,
      });
    });

    expect(
      screen.getByText(/Current owner:\s*Unassigned/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Assign owner/i }),
    ).toBeDisabled();
    expect(screen.getByText(/Owner update was saved/i)).toBeInTheDocument();
  });

  it("prevents owner assignment while a thread decision is pending", async () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-1",
          analysis_id: "analysis-1",
          compound_name: "Aspirin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Blocking claim needs review.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 2,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Assign owner for Aspirin/i), {
      target: { value: "user-2" },
    });
    expect(screen.getByRole("button", { name: /Assign owner/i })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /Resolve thread/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Assign owner/i }),
      ).toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Assign owner/i }));
    expect(assignMutateAsync).not.toHaveBeenCalled();
    expect(resolveMutateAsync).not.toHaveBeenCalled();
  });

  it("escalates the thread directly from the queue", async () => {
    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-2",
          analysis_id: "analysis-2",
          compound_name: "Ibuprofen",
          analysis_status: "completed",
          overall_risk: "medium",
          comment_body: "Needs legal handoff.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: false,
          is_unassigned: true,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Escalate/i }));

    await waitFor(() => {
      expect(escalateMutateAsync).toHaveBeenCalledWith({
        analysis_id: "analysis-2",
        comment_id: "comment-2",
        promote_to_under_review: true,
      });
    });
  });

  it("masks reviewer-list and action errors without exposing backend diagnostics", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCommentReviewers.mockReturnValue({
      data: [
        {
          id: "user-2",
          label: "Ada Lovelace",
          email: "ada@example.com",
          role: "attorney",
        },
      ],
      error: new Error("postgres://secret reviewer list failed"),
      isLoading: false,
    });
    assignMutateAsync.mockRejectedValueOnce(
      new Error("postgres://secret assignment failed"),
    );

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-3",
          analysis_id: "analysis-3",
          compound_name: "Naproxen",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Counsel assignment failed upstream.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    expect(
      screen.getByText(/Reviewer list temporarily unavailable/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Assign owner for Naproxen/i), {
      target: { value: "user-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Assign owner/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Owner update was not saved/i),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/postgres:\/\/secret assignment failed/i),
    ).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      "[ReviewQueueItemCard] Failed to assign owner",
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        message: expect.stringMatching(/postgres:\/\/secret/i),
      }),
    );

    consoleError.mockRestore();
  });

  it("separates saved actions from failed queue refreshes", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    onQueueRefresh.mockRejectedValueOnce(
      new Error("postgres://secret refresh failed"),
    );

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-4",
          analysis_id: "analysis-4",
          compound_name: "Celecoxib",
          analysis_status: "completed",
          overall_risk: "medium",
          comment_body: "Resolution should save before refresh.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: false,
          overdue_label: null,
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolve thread/i }));

    await waitFor(() => {
      expect(
        screen.getByText(
          /Thread resolution was saved, but the queue refresh failed/i,
        ),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/Thread resolution was not saved/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry refresh" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Resolution saved/i }),
    ).toBeDisabled();
    expect(consoleError).toHaveBeenCalledWith(
      "[ReviewQueueItemCard] Failed to refresh after thread resolution",
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        message: expect.stringMatching(/postgres:\/\/secret/i),
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /Resolution saved/i }));
    expect(resolveMutateAsync).toHaveBeenCalledTimes(1);

    consoleError.mockRestore();
  });

  it("prevents duplicate escalation after a saved action when queue refresh fails", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    onQueueRefresh.mockRejectedValueOnce(
      new Error("postgres://secret refresh failed"),
    );

    render(
      <ReviewQueueItemCard
        item={{
          id: "comment-5",
          analysis_id: "analysis-5",
          compound_name: "Atorvastatin",
          analysis_status: "completed",
          overall_risk: "high",
          comment_body: "Escalation should save before refresh.",
          assigned_to_name: null,
          assigned_to_email: null,
          is_mine: true,
          is_unassigned: true,
          is_overdue: true,
          overdue_label: "Overdue · 2d open",
          is_escalated: false,
          escalated_at: null,
          last_activity_at: "2026-04-18T10:30:00Z",
          updated_at: "2026-04-18T10:30:00Z",
          comment_count: 1,
        }}
        token="tok"
        onQueueRefresh={onQueueRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Escalate$/i }));
    expect(escalateMutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText("Confirm legal escalation")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm escalation/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Escalation was saved, but the queue refresh failed/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Escalated/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Escalated/i }));
    expect(escalateMutateAsync).toHaveBeenCalledTimes(1);

    consoleError.mockRestore();
  });
});
