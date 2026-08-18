import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AUTH_BOUNDARY_CHANGED_EVENT } from "@/lib/auth-events";

const mockUseReviewQueue = vi.fn();
const navigationMocks = vi.hoisted(() => ({
  replace: vi.fn(),
  pathname: "/reviews",
  searchParams: "",
}));

vi.mock("@/hooks/use-review-queue", () => ({
  useReviewQueue: (...args: unknown[]) => mockUseReviewQueue(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigationMocks.replace }),
  usePathname: () => navigationMocks.pathname,
  useSearchParams: () => new URLSearchParams(navigationMocks.searchParams),
}));

vi.mock("@/components/reviews/review-queue-item-card", () => ({
  ReviewQueueItemCard: ({
    item,
    selectionControl,
    actionsDisabled,
    actionPendingSourceId,
    onActionPendingChange,
  }: {
    item: { id: string; compound_name: string };
    selectionControl?: React.ReactNode;
    actionsDisabled?: boolean;
    actionPendingSourceId?: string;
    onActionPendingChange?: (sourceId: string, pending: boolean) => void;
  }) => (
    <div
      data-testid="review-queue-item-card"
      data-actions-disabled={String(Boolean(actionsDisabled))}
    >
      {selectionControl}
      <span data-testid="review-queue-item-name">{item.compound_name}</span>
      <button
        type="button"
        onClick={() =>
          onActionPendingChange?.(
            actionPendingSourceId ?? `item:${item.id}`,
            true,
          )
        }
      >
        Hold {item.compound_name} action
      </button>
      <button
        type="button"
        onClick={() =>
          onActionPendingChange?.(
            actionPendingSourceId ?? `item:${item.id}`,
            false,
          )
        }
      >
        Release {item.compound_name} action
      </button>
    </div>
  ),
}));

vi.mock("@/components/reviews/review-queue-bulk-toolbar", () => ({
  ReviewQueueBulkToolbar: ({
    selectedItems,
    onActionComplete,
    onClearSelection,
    actionsDisabled,
    actionPendingSourceId,
    onActionPendingChange,
  }: {
    selectedItems: Array<{ compound_name: string }>;
    onActionComplete?: (payload: {
      action: "assign" | "resolve" | "escalate";
      count: number;
      scopeLabel: string | null;
      sharedAnalysisId: string | null;
      assignedToLabel?: string | null;
    }) => void;
    onClearSelection?: () => void;
    actionsDisabled?: boolean;
    actionPendingSourceId?: string;
    onActionPendingChange?: (sourceId: string, pending: boolean) => void;
  }) =>
    selectedItems.length > 0 ? (
      <div
        data-testid="review-queue-bulk-toolbar"
        data-actions-disabled={String(Boolean(actionsDisabled))}
      >
        {selectedItems.length} visible threads selected
        <button
          type="button"
          onClick={() =>
            onActionPendingChange?.(actionPendingSourceId ?? "bulk", true)
          }
        >
          Hold bulk action
        </button>
        <button
          type="button"
          onClick={() =>
            onActionPendingChange?.(actionPendingSourceId ?? "bulk", false)
          }
        >
          Release bulk action
        </button>
        <button
          type="button"
          onClick={() => {
            onActionComplete?.({
              action: "resolve",
              count: selectedItems.length,
              scopeLabel: selectedItems[0]?.compound_name ?? null,
              sharedAnalysisId:
                selectedItems.length > 1 ? "analysis-scope" : "analysis-single",
            });
            onClearSelection?.();
          }}
        >
          Emit success
        </button>
      </div>
    ) : null,
}));

import { ReviewQueuePage } from "@/components/reviews/review-queue-page";

describe("ReviewQueuePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigationMocks.pathname = "/reviews";
    navigationMocks.searchParams = "";
    mockUseReviewQueue.mockReturnValue({
      data: {
        counts: {
          total: 3,
          mine: 1,
          unassigned: 1,
          overdue: 1,
          escalated: 1,
        },
        items: [
          {
            id: "rq-1",
            analysis_id: "analysis-1",
            compound_name: "Ibuprofen",
            analysis_status: "completed",
            overall_risk: "medium",
            comment_body: "Recent update",
            assigned_to_id: "user-1",
            assigned_to_name: "Alice Attorney",
            assigned_to_email: "alice@example.com",
            is_mine: true,
            is_unassigned: false,
            is_overdue: false,
            overdue_label: null,
            is_escalated: false,
            escalated_at: null,
            last_activity_at: "2026-04-18T12:00:00Z",
            updated_at: "2026-04-18T12:00:00Z",
            comment_count: 1,
          },
          {
            id: "rq-2",
            analysis_id: "analysis-2",
            compound_name: "Aspirin",
            analysis_status: "completed",
            overall_risk: "high",
            comment_body: "Overdue thread",
            assigned_to_id: null,
            assigned_to_name: null,
            assigned_to_email: null,
            is_mine: false,
            is_unassigned: true,
            is_overdue: true,
            overdue_label: "Overdue · 2d open",
            is_escalated: false,
            escalated_at: null,
            last_activity_at: "2026-04-18T08:00:00Z",
            updated_at: "2026-04-18T08:00:00Z",
            comment_count: 2,
          },
          {
            id: "rq-3",
            analysis_id: "analysis-3",
            compound_name: "Succinic acid",
            analysis_status: "completed",
            overall_risk: "low",
            comment_body: "Escalated thread",
            assigned_to_id: "user-2",
            assigned_to_name: "Bob Reviewer",
            assigned_to_email: "bob@example.com",
            is_mine: false,
            is_unassigned: false,
            is_overdue: false,
            overdue_label: null,
            is_escalated: true,
            escalated_at: "2026-04-18T09:00:00Z",
            last_activity_at: "2026-04-18T09:00:00Z",
            updated_at: "2026-04-18T09:00:00Z",
            comment_count: 4,
          },
        ],
        updated_at: "2026-04-18T12:00:00Z",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("sorts visible items and lets reviewers change the ordering", async () => {
    render(<ReviewQueuePage token="tok" />);

    expect(
      screen.getByTestId("review-queue-app-surface-header"),
    ).toHaveAttribute("data-praviar-app-surface-header");
    expect(screen.getByText("Legal Review Queue")).toBeInTheDocument();
    expect(screen.getByText("Open threads")).toBeInTheDocument();
    expect(screen.getByText("Active review handoffs")).toBeInTheDocument();
    expect(
      screen.getByText(/Current priority: Aspirin\./u),
    ).toBeInTheDocument();

    expect(
      screen
        .getAllByTestId("review-queue-item-name")
        .map((node) => node.textContent),
    ).toEqual(["Aspirin", "Succinic acid", "Ibuprofen"]);

    fireEvent.change(screen.getByLabelText("Queue ordering"), {
      target: { value: "recent" },
    });

    await waitFor(() => {
      expect(
        screen
          .getAllByTestId("review-queue-item-name")
          .map((node) => node.textContent),
      ).toEqual(["Ibuprofen", "Succinic acid", "Aspirin"]);
    });

    fireEvent.change(screen.getByLabelText("Queue ordering"), {
      target: { value: "compound" },
    });

    await waitFor(() => {
      expect(
        screen
          .getAllByTestId("review-queue-item-name")
          .map((node) => node.textContent),
      ).toEqual(["Aspirin", "Ibuprofen", "Succinic acid"]);
    });
  });

  it("uses singular and plural grammar in the overdue cockpit action", () => {
    const queueResult = mockUseReviewQueue();
    const { rerender } = render(<ReviewQueuePage token="tok" />);

    expect(
      screen.getByText(
        "1 overdue review thread needs a response before routine ownership cleanup.",
      ),
    ).toBeInTheDocument();

    mockUseReviewQueue.mockReturnValue({
      ...queueResult,
      data: {
        ...queueResult.data,
        counts: {
          ...queueResult.data.counts,
          overdue: 2,
        },
      },
    });
    rerender(<ReviewQueuePage token="tok" />);

    expect(
      screen.getByText(
        "2 overdue review threads need a response before routine ownership cleanup.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps queue filter and sort state in the URL without stale focus presets", async () => {
    navigationMocks.searchParams = "focus=my-overdue&source=workload";

    render(
      <ReviewQueuePage
        token="tok"
        initialFilter="overdue"
        initialReviewerScope="mine"
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Escalated: 1 org open thread/i }),
    );

    await waitFor(() => {
      expect(navigationMocks.replace).toHaveBeenLastCalledWith(
        "/reviews?source=workload&filter=escalated&sort=priority&scope=mine",
        { scroll: false },
      );
    });

    fireEvent.change(screen.getByLabelText("Queue ordering"), {
      target: { value: "recent" },
    });

    await waitFor(() => {
      expect(navigationMocks.replace).toHaveBeenLastCalledWith(
        "/reviews?source=workload&filter=escalated&sort=recent&scope=mine",
        { scroll: false },
      );
    });
  });

  it("tracks visible-item selection and surfaces the bulk toolbar", async () => {
    render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));

    await waitFor(() => {
      expect(
        screen.getByText(/3 visible threads selected/i),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /Clear selection/i }));

    await waitFor(() => {
      expect(
        screen.queryByText(/visible threads selected/i),
      ).not.toBeInTheDocument();
    });
  });

  it("locks queue filters, sort, and selection while an item action is pending", async () => {
    render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));

    await waitFor(() => {
      expect(
        screen.getByTestId("review-queue-bulk-toolbar"),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Hold Aspirin action/i }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Review queue worklist")).toHaveAttribute(
        "aria-busy",
        "true",
      );
    });

    expect(screen.getByLabelText("Queue ordering")).toBeDisabled();
    expect(
      screen.getByLabelText(/Select all visible mine threads/i),
    ).toBeDisabled();
    expect(screen.getByLabelText(/Select Aspirin thread/i)).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Escalated: 1 open thread/i }),
    ).toBeDisabled();
    expect(screen.getByTestId("review-queue-bulk-toolbar")).toHaveAttribute(
      "data-actions-disabled",
      "true",
    );
    expect(
      screen.getByText(/Applying review queue update/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Escalated: 1 open thread/i }),
    );
    expect(navigationMocks.replace).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: /Release Aspirin action/i }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Queue ordering")).toBeEnabled();
    });
  });

  it("locks parent queue controls while a bulk action is pending", async () => {
    render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));

    await waitFor(() => {
      expect(
        screen.getByTestId("review-queue-bulk-toolbar"),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Hold bulk action/i }));

    await waitFor(() => {
      expect(screen.getByLabelText("Review queue worklist")).toHaveAttribute(
        "aria-busy",
        "true",
      );
    });

    expect(screen.getByLabelText("Queue ordering")).toBeDisabled();
    expect(
      screen.getByLabelText(/Select all visible mine threads/i),
    ).toBeDisabled();
    expect(screen.getByLabelText(/Select Ibuprofen thread/i)).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Needs owner: 1 open thread/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: /Release bulk action/i }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Queue ordering")).toBeEnabled();
    });
  });

  it("prunes hidden selections when refreshed queue rows disappear", async () => {
    const removableItem = {
      id: "rq-removable",
      analysis_id: "analysis-removable",
      compound_name: "Removable case",
      analysis_status: "completed",
      overall_risk: "medium",
      comment_body: "Selected before refresh.",
      assigned_to_id: "user-1",
      assigned_to_name: "Alice Attorney",
      assigned_to_email: "alice@example.com",
      is_mine: true,
      is_unassigned: false,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      escalated_at: null,
      last_activity_at: "2026-04-18T12:00:00Z",
      updated_at: "2026-04-18T12:00:00Z",
      comment_count: 1,
    };
    const stableItem = {
      ...removableItem,
      id: "rq-stable",
      analysis_id: "analysis-stable",
      compound_name: "Stable case",
    };
    let currentItems = [removableItem, stableItem];
    mockUseReviewQueue.mockImplementation(() => ({
      data: {
        counts: {
          total: currentItems.length,
          mine: currentItems.length,
          unassigned: 0,
          overdue: 0,
          escalated: 0,
        },
        items: currentItems,
        updated_at: "2026-04-18T12:00:00Z",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    const { rerender } = render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select Removable case thread/i));

    await waitFor(() => {
      expect(
        screen.getByText(/1 visible threads selected/i),
      ).toBeInTheDocument();
    });

    currentItems = [stableItem];
    rerender(<ReviewQueuePage token="tok" />);

    await waitFor(() => {
      expect(
        screen.queryByText(/visible threads selected/i),
      ).not.toBeInTheDocument();
    });

    currentItems = [removableItem, stableItem];
    rerender(<ReviewQueuePage token="tok" />);

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Select Removable case thread/i),
      ).not.toBeChecked();
    });
  });

  it("keeps selected review queue rows when a refetch returns the same IDs", async () => {
    const selectedItem = {
      id: "rq-selected",
      analysis_id: "analysis-selected",
      compound_name: "Selected case",
      analysis_status: "completed",
      overall_risk: "medium",
      comment_body: "Selected before same-data refresh.",
      assigned_to_id: "user-1",
      assigned_to_name: "Alice Attorney",
      assigned_to_email: "alice@example.com",
      is_mine: true,
      is_unassigned: false,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      escalated_at: null,
      last_activity_at: "2026-04-18T12:00:00Z",
      updated_at: "2026-04-18T12:00:00Z",
      comment_count: 1,
    };
    const secondItem = {
      ...selectedItem,
      id: "rq-second",
      analysis_id: "analysis-second",
      compound_name: "Second case",
    };
    let currentItems = [selectedItem, secondItem];
    mockUseReviewQueue.mockImplementation(() => ({
      data: {
        counts: {
          total: currentItems.length,
          mine: currentItems.length,
          unassigned: 0,
          overdue: 0,
          escalated: 0,
        },
        items: currentItems,
        updated_at: "2026-04-18T12:00:00Z",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    const { rerender } = render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select Selected case thread/i));

    await waitFor(() => {
      expect(
        screen.getByText(/1 visible threads selected/i),
      ).toBeInTheDocument();
    });

    currentItems = currentItems.map((item) => ({ ...item }));
    rerender(<ReviewQueuePage token="tok" />);

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Select Selected case thread/i),
      ).toBeChecked();
      expect(
        screen.getByText(/1 visible threads selected/i),
      ).toBeInTheDocument();
    });
  });

  it("uses mobile-first queue filters and touch-safe controls", () => {
    render(<ReviewQueuePage token="tok" />);

    expect(screen.getByTestId("review-queue-filter-grid")).toHaveClass(
      "grid-cols-1",
      "sm:grid-cols-2",
      "xl:grid-cols-4",
    );
    expect(screen.getByLabelText("Queue ordering")).toHaveClass(
      "h-11",
      "w-full",
    );
    expect(screen.getByLabelText("Queue ordering")).not.toHaveClass("sm:h-9");
    expect(
      screen.getByText("Select visible items").closest("label"),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByLabelText(/Select all visible mine threads/i),
    ).toHaveClass("absolute", "h-full", "w-full");
    expect(screen.getByLabelText(/Select Aspirin thread/i)).toHaveClass(
      "absolute",
      "h-full",
      "w-full",
    );
    expect(
      screen.getByLabelText(/Select Aspirin thread/i).closest("label"),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", { name: /Clear selection/i }),
    ).toHaveClass("min-h-11", "w-full");
    expect(screen.getByText("Evidence readiness")).toBeInTheDocument();
    expect(screen.getByText("1 escalated")).toBeInTheDocument();
    expect(screen.getByText("1 overdue")).toBeInTheDocument();
    expect(screen.getByText("1 unassigned")).toBeInTheDocument();
    expect(
      screen.getByText(/Batch reviewer updates require confirmation/i),
    ).toBeInTheDocument();
    expect(screen.getByText("18 Apr, 12:00 UTC")).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
  });

  it("does not describe a loaded empty queue slice as pending sync", () => {
    mockUseReviewQueue.mockReturnValue({
      data: {
        counts: {
          total: 2,
          mine: 0,
          unassigned: 1,
          overdue: 1,
          escalated: 0,
        },
        items: [],
        updated_at: null,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ReviewQueuePage token="tok" />);

    expect(screen.getByText("Loaded")).toBeInTheDocument();
    expect(screen.queryByText("Pending sync")).not.toBeInTheDocument();
    expect(screen.getByText(/No mine threads right now/i)).toBeInTheDocument();
  });

  it("uses a touch-safe retry control in the error state", () => {
    const refetch = vi.fn();
    mockUseReviewQueue.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: new Error("postgres://secret reviewer queue failed"),
      refetch,
    });

    render(<ReviewQueuePage token="tok" />);

    expect(screen.getByRole("button", { name: "Retry" })).toHaveClass(
      "min-h-11",
      "w-full",
    );
    expect(screen.getByTestId("review-queue-temporary")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(
      screen.getByText(
        /existing review assignments and thread states are unchanged/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Keep reviewer assignments and thread states unchanged/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("keeps stale review queue rows visible but locks actions when a refresh fails", () => {
    const refetch = vi.fn();
    mockUseReviewQueue.mockReturnValue({
      data: {
        counts: {
          total: 1,
          mine: 1,
          unassigned: 0,
          overdue: 0,
          escalated: 0,
        },
        items: [
          {
            id: "rq-7",
            analysis_id: "analysis-7",
            compound_name: "Stale visible case",
            analysis_status: "completed",
            overall_risk: "medium",
            comment_body: "Visible while refresh is failing.",
            assigned_to_id: "user-1",
            assigned_to_name: "Alice Attorney",
            assigned_to_email: "alice@example.com",
            is_mine: true,
            is_unassigned: false,
            is_overdue: false,
            overdue_label: null,
            is_escalated: false,
            escalated_at: null,
            last_activity_at: "2026-04-18T12:00:00Z",
            updated_at: "2026-04-18T12:00:00Z",
            comment_count: 1,
          },
        ],
        updated_at: "2026-04-18T12:00:00Z",
      },
      isLoading: false,
      isError: true,
      error: new Error("postgres://secret refresh failed"),
      refetch,
    });

    render(<ReviewQueuePage token="tok" />);

    expect(screen.getByText("Stale visible case")).toBeInTheDocument();
    expect(
      screen.getByText(/Existing reviewer data remains visible/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/queue actions are locked until the queue refreshes/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Queue ordering")).toBeDisabled();
    expect(
      screen.getByLabelText(/Select all visible mine threads/i),
    ).toBeDisabled();
    expect(
      screen.getByLabelText(/Select Stale visible case thread/i),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Needs owner: 0 open threads/i }),
    ).toBeDisabled();
    expect(screen.getByTestId("review-queue-item-card")).toHaveAttribute(
      "data-actions-disabled",
      "true",
    );

    fireEvent.click(screen.getByLabelText(/Select Stale visible case thread/i));
    expect(
      screen.queryByTestId("review-queue-bulk-toolbar"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry refresh" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("does not show a false empty queue while access is unavailable", () => {
    mockUseReviewQueue.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ReviewQueuePage token={null} />);

    expect(screen.getByTestId("review-queue-auth")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(
      screen.getByText("Checking review queue access"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Open threads")).not.toBeInTheDocument();
    expect(screen.queryByText(/No mine threads/i)).not.toBeInTheDocument();
  });

  it("shows queue feedback after a bulk action completes", async () => {
    render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));

    await waitFor(() => {
      expect(
        screen.getByTestId("review-queue-bulk-toolbar"),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Emit success/i }));

    await waitFor(() => {
      expect(screen.getByText("Queue updated")).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(
      screen.getByText("Resolved Aspirin scope (3 threads)."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Resolved threads move out of open review queues once the refreshed slice lands.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("review-queue-bulk-toolbar"),
    ).not.toBeInTheDocument();

    const dismissButton = screen.getByRole("button", {
      name: "Dismiss update",
    });
    await waitFor(() => {
      expect(dismissButton).toHaveFocus();
    });

    fireEvent.click(dismissButton);

    await waitFor(() => {
      expect(screen.queryByText("Queue updated")).not.toBeInTheDocument();
    });
  });

  it("clears selected review queue rows and feedback on auth boundary changes", async () => {
    render(<ReviewQueuePage token="tok" />);

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));

    await waitFor(() => {
      expect(
        screen.getByTestId("review-queue-bulk-toolbar"),
      ).toBeInTheDocument();
    });

    act(() => {
      window.dispatchEvent(new CustomEvent(AUTH_BOUNDARY_CHANGED_EVENT));
    });

    await waitFor(() => {
      expect(
        screen.queryByTestId("review-queue-bulk-toolbar"),
      ).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/Select all visible mine threads/i));
    fireEvent.click(screen.getByRole("button", { name: /Emit success/i }));

    await waitFor(() => {
      expect(screen.getByText("Queue updated")).toBeInTheDocument();
    });

    act(() => {
      window.dispatchEvent(new CustomEvent(AUTH_BOUNDARY_CHANGED_EVENT));
    });

    await waitFor(() => {
      expect(screen.queryByText("Queue updated")).not.toBeInTheDocument();
    });
  });

  it("supports reviewer-scoped overdue deep links without breaking filter changes", async () => {
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        if (filter === "escalated") {
          return {
            data: {
              counts: {
                total: 2,
                mine: 1,
                unassigned: 0,
                overdue: 0,
                escalated: 2,
              },
              items: [
                {
                  id: "rq-4",
                  analysis_id: "analysis-4",
                  compound_name: "My escalated case",
                  analysis_status: "completed",
                  overall_risk: "high",
                  comment_body: "Escalated by counsel",
                  assigned_to_id: "user-1",
                  assigned_to_name: "Alice Attorney",
                  assigned_to_email: "alice@example.com",
                  is_mine: true,
                  is_unassigned: false,
                  is_overdue: false,
                  overdue_label: null,
                  is_escalated: true,
                  escalated_at: "2026-04-18T11:00:00Z",
                  last_activity_at: "2026-04-18T11:00:00Z",
                  updated_at: "2026-04-18T11:00:00Z",
                  comment_count: 2,
                },
                {
                  id: "rq-5",
                  analysis_id: "analysis-5",
                  compound_name: "Other escalated case",
                  analysis_status: "completed",
                  overall_risk: "high",
                  comment_body: "Escalated elsewhere",
                  assigned_to_id: "user-2",
                  assigned_to_name: "Bob Reviewer",
                  assigned_to_email: "bob@example.com",
                  is_mine: false,
                  is_unassigned: false,
                  is_overdue: false,
                  overdue_label: null,
                  is_escalated: true,
                  escalated_at: "2026-04-18T10:00:00Z",
                  last_activity_at: "2026-04-18T10:00:00Z",
                  updated_at: "2026-04-18T10:00:00Z",
                  comment_count: 1,
                },
              ],
              updated_at: "2026-04-18T11:00:00Z",
            },
            isLoading: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        }

        return {
          data: {
            counts: {
              total: 2,
              mine: 1,
              unassigned: 1,
              overdue: 2,
              escalated: 0,
            },
            items: [
              {
                id: "rq-2",
                analysis_id: "analysis-2",
                compound_name: "My overdue case",
                analysis_status: "completed",
                overall_risk: "high",
                comment_body: "Overdue thread",
                assigned_to_id: "user-1",
                assigned_to_name: "Alice Attorney",
                assigned_to_email: "alice@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: true,
                overdue_label: "Overdue · 2d open",
                is_escalated: false,
                escalated_at: null,
                last_activity_at: "2026-04-18T08:00:00Z",
                updated_at: "2026-04-18T08:00:00Z",
                comment_count: 2,
              },
              {
                id: "rq-6",
                analysis_id: "analysis-6",
                compound_name: "Other overdue case",
                analysis_status: "completed",
                overall_risk: "medium",
                comment_body: "Other overdue thread",
                assigned_to_id: "user-2",
                assigned_to_name: "Bob Reviewer",
                assigned_to_email: "bob@example.com",
                is_mine: false,
                is_unassigned: false,
                is_overdue: true,
                overdue_label: "Overdue · 1d open",
                is_escalated: false,
                escalated_at: null,
                last_activity_at: "2026-04-18T07:00:00Z",
                updated_at: "2026-04-18T07:00:00Z",
                comment_count: 1,
              },
            ],
            updated_at: "2026-04-18T08:00:00Z",
          },
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    render(
      <ReviewQueuePage
        token="tok"
        initialFilter="overdue"
        initialReviewerScope="mine"
      />,
    );

    expect(screen.getAllByText("Assigned to you").length).toBeGreaterThan(0);
    expect(screen.getByText("Org threads")).toBeInTheDocument();
    expect(screen.getByText("My urgent review")).toBeInTheDocument();
    expect(screen.getByText("My visible ownership")).toBeInTheDocument();
    expect(
      screen.getByText("Showing your assigned overdue workload"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /1 assigned-to-you thread shown from 2 current-filter overdue threads/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reviewer-filtered queue snapshot"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/org snapshot/i)).not.toBeInTheDocument();
    expect(screen.getByText("My overdue threads")).toBeInTheDocument();
    expect(
      screen
        .getAllByTestId("review-queue-item-name")
        .map((node) => node.textContent),
    ).toEqual(["My overdue case"]);

    fireEvent.click(screen.getByRole("button", { name: /Escalated/i }));

    await waitFor(() => {
      expect(mockUseReviewQueue).toHaveBeenLastCalledWith("tok", "escalated");
      expect(screen.getByText("My escalated threads")).toBeInTheDocument();
      expect(
        screen
          .getAllByTestId("review-queue-item-name")
          .map((node) => node.textContent),
      ).toEqual(["My escalated case"]);
    });
  });

  it("supports initial reviewer-scoped escalated mounts", () => {
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        if (filter === "escalated") {
          return {
            data: {
              counts: {
                total: 2,
                mine: 1,
                unassigned: 0,
                overdue: 0,
                escalated: 2,
              },
              items: [
                {
                  id: "rq-4",
                  analysis_id: "analysis-4",
                  compound_name: "My escalated case",
                  analysis_status: "completed",
                  overall_risk: "high",
                  comment_body: "Escalated by counsel",
                  assigned_to_id: "user-1",
                  assigned_to_name: "Alice Attorney",
                  assigned_to_email: "alice@example.com",
                  is_mine: true,
                  is_unassigned: false,
                  is_overdue: false,
                  overdue_label: null,
                  is_escalated: true,
                  escalated_at: "2026-04-18T11:00:00Z",
                  last_activity_at: "2026-04-18T11:00:00Z",
                  updated_at: "2026-04-18T11:00:00Z",
                  comment_count: 2,
                },
                {
                  id: "rq-5",
                  analysis_id: "analysis-5",
                  compound_name: "Other escalated case",
                  analysis_status: "completed",
                  overall_risk: "high",
                  comment_body: "Escalated elsewhere",
                  assigned_to_id: "user-2",
                  assigned_to_name: "Bob Reviewer",
                  assigned_to_email: "bob@example.com",
                  is_mine: false,
                  is_unassigned: false,
                  is_overdue: false,
                  overdue_label: null,
                  is_escalated: true,
                  escalated_at: "2026-04-18T10:00:00Z",
                  last_activity_at: "2026-04-18T10:00:00Z",
                  updated_at: "2026-04-18T10:00:00Z",
                  comment_count: 1,
                },
              ],
              updated_at: "2026-04-18T11:00:00Z",
            },
            isLoading: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        }

        return {
          data: {
            counts: {
              total: 0,
              mine: 0,
              unassigned: 0,
              overdue: 0,
              escalated: 2,
            },
            items: [],
            updated_at: "2026-04-18T11:00:00Z",
          },
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    render(
      <ReviewQueuePage
        token="tok"
        initialFilter="escalated"
        initialReviewerScope="mine"
      />,
    );

    expect(screen.getAllByText("Assigned to you").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Showing your assigned escalated workload"),
    ).toBeInTheDocument();
    expect(screen.getByText("My escalated threads")).toBeInTheDocument();
    expect(
      screen
        .getAllByTestId("review-queue-item-name")
        .map((node) => node.textContent),
    ).toEqual(["My escalated case"]);
  });
});
