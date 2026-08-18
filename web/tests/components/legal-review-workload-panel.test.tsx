import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseReviewQueue = vi.fn();
const principalState = vi.hoisted(() => ({
  role: "attorney",
  riskRatingsRestricted: false,
}));
const mockLegalReviewSpotlightActions = vi.fn(
  ({
    item,
    mode = "spotlight",
  }: {
    item: { id: string };
    mode?: "spotlight" | "inline";
  }) => (
    <div
      data-testid={
        mode === "inline"
          ? "legal-review-inline-actions"
          : "legal-review-spotlight-actions"
      }
      data-item-id={item.id}
      data-item-variant={mode}
    />
  ),
);
const mockReviewQueueBulkToolbar = vi.fn(
  ({
    selectedItems,
    mode = "full",
    onActionComplete,
    onClearSelection,
  }: {
    selectedItems: Array<{ id: string }>;
    mode?: "full" | "compact";
    onActionComplete?: (payload: {
      action: "assign" | "resolve" | "escalate";
      count: number;
      scopeLabel: string | null;
      sharedAnalysisId: string | null;
      assignedToLabel?: string | null;
    }) => void;
    onClearSelection?: () => void;
  }) =>
    selectedItems.length > 0 ? (
      <div
        data-testid="review-queue-bulk-toolbar"
        data-selected-count={selectedItems.length}
        data-mode={mode}
      >
        {selectedItems.length} selected
        <button
          type="button"
          onClick={() => {
            onActionComplete?.({
              action: "resolve",
              count: selectedItems.length,
              scopeLabel: "Celecoxib",
              sharedAnalysisId:
                selectedItems.length > 1 ? "ana-scope" : "ana-3",
            });
            onClearSelection?.();
          }}
        >
          Emit success
        </button>
      </div>
    ) : null,
);

vi.mock("@/hooks/use-review-queue", () => ({
  useReviewQueue: (...args: unknown[]) => mockUseReviewQueue(...args),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      role: principalState.role,
      risk_ratings_restricted: principalState.riskRatingsRestricted,
    },
  }),
}));

vi.mock("@/components/dashboard/legal-review-spotlight-actions", () => ({
  LegalReviewSpotlightActions: (...args: unknown[]) =>
    mockLegalReviewSpotlightActions(...args),
}));

vi.mock("@/components/reviews/review-queue-bulk-toolbar", () => ({
  ReviewQueueBulkToolbar: (...args: unknown[]) =>
    mockReviewQueueBulkToolbar(...args),
}));

import { LegalReviewWorkloadPanel } from "@/components/dashboard/legal-review-workload-panel";
import { REVIEW_QUEUE_LOAD_ERROR_COPY } from "@/components/reviews/review-queue-errors";

function renderPanel() {
  return render(<LegalReviewWorkloadPanel token="tok" />);
}

describe("LegalReviewWorkloadPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    principalState.role = "attorney";
    principalState.riskRatingsRestricted = false;
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        const queueByFilter: Record<string, unknown> = {
          mine: {
            counts: {
              total: 5,
              mine: 2,
              unassigned: 1,
              overdue: 2,
              escalated: 3,
            },
            items: [
              {
                id: "rq-3",
                analysis_id: "ana-3",
                compound_name: "Celecoxib",
                analysis_status: "completed",
                overall_risk: "medium",
                comment_body:
                  "Counsel follow-up needed on continuation exposure.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: false,
                overdue_label: null,
                is_escalated: true,
                escalated_at: "2026-04-18T07:00:00Z",
                queue_age_hours: 37,
                last_activity_at: "2026-04-18T09:45:00Z",
                updated_at: "2026-04-18T09:45:00Z",
                comment_count: 2,
              },
              {
                id: "rq-1",
                analysis_id: "ana-1",
                compound_name: "Aspirin",
                analysis_status: "completed",
                overall_risk: "high",
                comment_body:
                  "Attorney review requested for the lead claim chart.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: true,
                overdue_label: "Overdue · 2d open",
                is_escalated: true,
                escalated_at: "2026-04-18T08:15:00Z",
                queue_age_hours: 52,
                last_activity_at: "2026-04-18T10:30:00Z",
                updated_at: "2026-04-18T10:30:00Z",
                comment_count: 3,
              },
            ],
            updated_at: "2026-04-18T10:30:00Z",
          },
          unassigned: {
            counts: {
              total: 5,
              mine: 2,
              unassigned: 1,
              overdue: 2,
              escalated: 3,
            },
            items: [
              {
                id: "rq-2",
                analysis_id: "ana-2",
                compound_name: "Ibuprofen",
                analysis_status: "running",
                overall_risk: "medium",
                comment_body: "Unassigned thread awaiting review.",
                assigned_to_name: null,
                assigned_to_email: null,
                is_mine: false,
                is_unassigned: true,
                is_overdue: false,
                overdue_label: null,
                is_escalated: false,
                escalated_at: null,
                queue_age_hours: 12,
                last_activity_at: "2026-04-18T09:05:00Z",
                updated_at: "2026-04-18T09:05:00Z",
                comment_count: 1,
              },
            ],
            updated_at: "2026-04-18T10:30:00Z",
          },
          overdue: {
            counts: {
              total: 5,
              mine: 2,
              unassigned: 1,
              overdue: 2,
              escalated: 3,
            },
            items: [],
            updated_at: "2026-04-18T10:30:00Z",
          },
          escalated: {
            counts: {
              total: 5,
              mine: 2,
              unassigned: 1,
              overdue: 2,
              escalated: 3,
            },
            items: [],
            updated_at: "2026-04-18T10:30:00Z",
          },
        };

        return {
          data: queueByFilter[filter] ?? queueByFilter.mine,
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );
  });

  it("renders counts and switches filters without breaking the dashboard", () => {
    renderPanel();

    expect(screen.getByText("Legal review workload")).toBeInTheDocument();
    expect(screen.getByText("Legal queue pressure")).toBeInTheDocument();
    expect(screen.getByText("Your workload")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mine 2/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Mine 2/ })).toHaveClass(
      "min-h-16",
    );
    expect(screen.getByText("2 assigned to you")).toBeInTheDocument();
    expect(screen.getByText("1 my overdue")).toBeInTheDocument();
    expect(screen.getByText("1 at risk next")).toBeInTheDocument();
    expect(screen.getByText("2 my escalations")).toBeInTheDocument();
    expect(screen.getByText("1 of yours overdue")).toBeInTheDocument();
    expect(screen.getByText("Assigned to you")).toBeInTheDocument();
    expect(screen.getByText("My overdue")).toBeInTheDocument();
    expect(screen.getByText("My escalations")).toBeInTheDocument();
    expect(screen.getByText("Needs owner")).toBeInTheDocument();
    expect(
      screen.getByText("Resolve from your owned queue."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("2 pressured threads currently sit in your queue."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Aging buckets: 1 overdue · 1 at risk next · 0 watch window",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Oldest owned update/i)).toBeInTheDocument();
    expect(screen.getByText("Owned spotlight")).toBeInTheDocument();
    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toHaveAttribute("data-item-id", "rq-1");
    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toHaveAttribute("data-item-variant", "spotlight");
    expect(screen.getByRole("link", { name: /View report/i })).toHaveAttribute(
      "href",
      "/analyses/ana-1/report",
    );
    expect(screen.getByRole("link", { name: /View report/i })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getAllByRole("link", { name: /Open my queue/i }),
    ).toHaveLength(2);
    screen.getAllByRole("link", { name: /Open my queue/i }).forEach((link) => {
      expect(link).toHaveAttribute(
        "href",
        "/reviews?filter=mine&sort=priority",
      );
      expect(link).toHaveClass("min-h-11");
    });
    expect(
      screen.getByRole("link", { name: /Open my overdue/i }),
    ).toHaveAttribute("href", "/reviews?focus=my-overdue&sort=priority");
    expect(
      screen.getByRole("link", { name: /Open my escalations/i }),
    ).toHaveAttribute("href", "/reviews?focus=my-escalated&sort=priority");
    expect(
      screen.getByRole("link", { name: /Open this slice/i }),
    ).toHaveAttribute("href", "/reviews?filter=mine&sort=priority");
    expect(screen.getByRole("link", { name: /Open this slice/i })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByText(/Showing 2 mine items/i).parentElement).toHaveClass(
      "flex-col",
      "gap-3",
      "sm:flex-row",
    );
    const aspirinLink = screen.getByRole("link", { name: /Aspirin/i });
    expect(aspirinLink).toBeInTheDocument();
    expect(within(aspirinLink).getByText("Mine")).toBeInTheDocument();
    expect(
      within(aspirinLink).getByText("Overdue · 2d open"),
    ).toBeInTheDocument();

    const celecoxibLink = screen.getByRole("link", { name: /Celecoxib/i });
    expect(celecoxibLink).toBeInTheDocument();
    expect(within(celecoxibLink).getByText("Mine")).toBeInTheDocument();
    expect(
      within(celecoxibLink).getByText("At risk next · 37h open"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Unassigned 1/ }));

    expect(screen.getByText("Ibuprofen")).toBeInTheDocument();
    expect(
      screen.getByText("Unassigned thread awaiting review."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ibuprofen/i })).toHaveAttribute(
      "href",
      "/analyses/ana-2",
    );
    screen.getAllByRole("link", { name: /View run/i }).forEach((link) => {
      expect(link).toHaveAttribute("href", "/analyses/ana-2");
    });
    expect(
      screen.getByRole("link", { name: /Open this slice/i }),
    ).toHaveAttribute("href", "/reviews?filter=unassigned&sort=priority");
    expect(screen.getByRole("button", { name: /Unassigned 1/ })).toHaveClass(
      "min-h-16",
    );
  });

  it("wraps long queue row comments and assignee identifiers", () => {
    const longCompound =
      "NintedanibContinuationDesignAroundProgramWithExtendedSaltFormAndMethodOfTreatmentScope";
    const longComment =
      "Counsel flagged https://diligence.example/review/very-long-provider-evidence-token-without-natural-breakpoints-and-markush-substitution-history for immediate review.";
    const longAssignee =
      "external.counsel.with.long.crossborder.identity@life-sciences-diligence.example";
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        const queue = {
          counts: {
            total: 1,
            mine: 1,
            unassigned: 0,
            overdue: 1,
            escalated: 1,
          },
          items: [
            {
              id: "rq-long",
              analysis_id: "ana-long",
              compound_name: longCompound,
              analysis_status: "completed",
              overall_risk: "high",
              comment_body: longComment,
              assigned_to_name: null,
              assigned_to_email: longAssignee,
              is_mine: true,
              is_unassigned: false,
              is_overdue: true,
              overdue_label: "Overdue · 5d open",
              is_escalated: true,
              escalated_at: "2026-04-18T08:15:00Z",
              queue_age_hours: 128,
              last_activity_at: "2026-04-18T10:30:00Z",
              updated_at: "2026-04-18T10:30:00Z",
              comment_count: 4,
            },
          ],
          updated_at: "2026-04-18T10:30:00Z",
        };

        return {
          data: filter === "mine" ? queue : { ...queue, items: [] },
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    renderPanel();

    const queueLink = screen.getByRole("link", {
      name: /NintedanibContinuationDesignAroundProgram/i,
    });
    expect(within(queueLink).getByText(longCompound)).toHaveClass(
      "min-w-0",
      "truncate",
    );
    expect(screen.getByText(longComment)).toHaveClass(
      "line-clamp-2",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longAssignee)).toHaveClass(
      "min-w-0",
      "[overflow-wrap:anywhere]",
    );
  });

  it("renders when Array.prototype.toSorted is unavailable", () => {
    const arrayPrototype = Array.prototype as Array<unknown> & {
      toSorted?: unknown;
    };
    const originalToSorted = arrayPrototype.toSorted;
    Object.defineProperty(Array.prototype, "toSorted", {
      configurable: true,
      value: undefined,
    });

    try {
      renderPanel();
      expect(screen.getByText("Legal review workload")).toBeInTheDocument();
      expect(screen.getByText("Owned spotlight")).toBeInTheDocument();
    } finally {
      if (originalToSorted === undefined) {
        delete arrayPrototype.toSorted;
      } else {
        Object.defineProperty(Array.prototype, "toSorted", {
          configurable: true,
          value: originalToSorted,
        });
      }
    }
  });

  it("uses safe copy when dashboard review queue loading fails", () => {
    mockUseReviewQueue.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("postgres://secret-host SELECT * FROM review_queue"),
      refetch: vi.fn(),
    });

    renderPanel();

    expect(screen.getByText(REVIEW_QUEUE_LOAD_ERROR_COPY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.queryByText(
        /postgres:\/\/secret-host|SELECT \* FROM review_queue/i,
      ),
    ).not.toBeInTheDocument();
  });

  it("opens an inline action tray for non-spotlight queue rows", () => {
    renderPanel();

    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toHaveAttribute("data-item-id", "rq-1");
    expect(
      screen.queryByTestId("legal-review-inline-actions"),
    ).not.toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Quick actions/i })).toHaveClass(
      "min-h-11",
    );
    fireEvent.click(screen.getByRole("button", { name: /Quick actions/i }));

    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toHaveAttribute("data-item-id", "rq-1");
    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toHaveAttribute("data-item-variant", "spotlight");
    expect(screen.getByTestId("legal-review-inline-actions")).toHaveAttribute(
      "data-item-id",
      "rq-3",
    );
    expect(screen.getByTestId("legal-review-inline-actions")).toHaveAttribute(
      "data-item-variant",
      "inline",
    );
  });

  it("selects a visible dashboard row and shows the compact bulk-action tray", () => {
    renderPanel();

    expect(screen.getByRole("link", { name: /Aspirin/i })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Celecoxib/i }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByLabelText(/Select Celecoxib for bulk actions/i),
    );
    expect(
      screen.getByLabelText(/Select Celecoxib for bulk actions/i),
    ).toHaveClass("min-h-11");

    expect(screen.getByTestId("review-queue-bulk-toolbar")).toHaveAttribute(
      "data-selected-count",
      "1",
    );
    expect(screen.getByTestId("review-queue-bulk-toolbar")).toHaveAttribute(
      "data-mode",
      "compact",
    );
    expect(screen.getByText("Shared scope ready")).toBeInTheDocument();
    expect(
      screen.getByText("Owner assignment is ready for Celecoxib."),
    ).toBeInTheDocument();
  });

  it("shows a success banner after a dashboard bulk action completes", () => {
    renderPanel();

    fireEvent.click(
      screen.getByLabelText(/Select Celecoxib for bulk actions/i),
    );
    fireEvent.click(screen.getByRole("button", { name: /Emit success/i }));

    expect(screen.getByText("Queue updated")).toBeInTheDocument();
    expect(screen.getByText("Resolved Celecoxib.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Resolved threads move out of open review queues once the refreshed slice lands.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("review-queue-bulk-toolbar"),
    ).not.toBeInTheDocument();
  });

  it("offers scope shortcuts that replace mixed selections with one shared analysis scope", () => {
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        const queueByFilter: Record<string, unknown> = {
          mine: {
            counts: {
              total: 3,
              mine: 3,
              unassigned: 0,
              overdue: 1,
              escalated: 1,
            },
            items: [
              {
                id: "rq-scope-1",
                analysis_id: "ana-scope",
                compound_name: "Celecoxib",
                analysis_status: "completed",
                overall_risk: "high",
                comment_body: "Lead thread awaiting counsel review.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: true,
                overdue_label: "Overdue · 2d open",
                is_escalated: true,
                escalated_at: "2026-04-18T08:15:00Z",
                queue_age_hours: 52,
                last_activity_at: "2026-04-18T10:30:00Z",
                updated_at: "2026-04-18T10:30:00Z",
                comment_count: 3,
              },
              {
                id: "rq-scope-2",
                analysis_id: "ana-scope",
                compound_name: "Celecoxib follow-up",
                analysis_status: "completed",
                overall_risk: "medium",
                comment_body:
                  "Follow-up design-around question on the same analysis.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: false,
                overdue_label: null,
                is_escalated: true,
                escalated_at: "2026-04-18T07:00:00Z",
                queue_age_hours: 37,
                last_activity_at: "2026-04-18T09:45:00Z",
                updated_at: "2026-04-18T09:45:00Z",
                comment_count: 2,
              },
              {
                id: "rq-scope-3",
                analysis_id: "ana-other",
                compound_name: "Ibuprofen",
                analysis_status: "running",
                overall_risk: "medium",
                comment_body: "Separate thread from another analysis.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: false,
                overdue_label: null,
                is_escalated: false,
                escalated_at: null,
                queue_age_hours: 12,
                last_activity_at: "2026-04-18T09:05:00Z",
                updated_at: "2026-04-18T09:05:00Z",
                comment_count: 1,
              },
            ],
            updated_at: "2026-04-18T10:30:00Z",
          },
        };

        return {
          data: queueByFilter[filter] ?? queueByFilter.mine,
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    renderPanel();

    const scopeButton = screen.getByRole("button", {
      name: /Select Celecoxib scope \(2\)/i,
    });
    expect(scopeButton).toBeInTheDocument();
    expect(scopeButton).toHaveClass(
      "whitespace-normal",
      "[overflow-wrap:anywhere]",
      "min-h-11",
    );
    expect(
      screen.getByText(
        /Bulk owner assignment unlocks once the selected threads share one review scope\./i,
      ),
    ).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Select visible/i })).toHaveClass(
      "min-h-11",
    );
    fireEvent.click(screen.getByRole("button", { name: /Select visible/i }));

    expect(screen.getByText("Mixed scope selected")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Bulk resolve and escalation are ready, but owner assignment needs one shared analysis scope\./i,
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Select Celecoxib scope \(2\)/i }),
    );

    expect(screen.getByTestId("review-queue-bulk-toolbar")).toHaveAttribute(
      "data-selected-count",
      "2",
    );
    expect(
      screen.getByText(/showing 3 mine items · 2 selected/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Celecoxib scope selected/i)).toBeInTheDocument();
    expect(screen.getByText("Shared scope ready")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Bulk owner assignment is ready for Celecoxib scope (2 threads).",
      ),
    ).toBeInTheDocument();
  });

  it("keeps reviewer-owned aging emphasis visible before items go overdue", () => {
    mockUseReviewQueue.mockImplementation(
      (_token: string | null, filter: string) => {
        const queueByFilter: Record<string, unknown> = {
          mine: {
            counts: {
              total: 2,
              mine: 2,
              unassigned: 0,
              overdue: 0,
              escalated: 0,
            },
            items: [
              {
                id: "rq-pre-1",
                analysis_id: "ana-pre-1",
                compound_name: "Flurbiprofen",
                analysis_status: "completed",
                overall_risk: "medium",
                comment_body:
                  "Recent owned thread that still has room before SLA pressure.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: false,
                overdue_label: null,
                is_escalated: false,
                escalated_at: null,
                queue_age_hours: 6,
                last_activity_at: "2026-04-18T11:45:00Z",
                updated_at: "2026-04-18T11:45:00Z",
                comment_count: 1,
              },
              {
                id: "rq-pre-2",
                analysis_id: "ana-pre-2",
                compound_name: "Naproxen",
                analysis_status: "completed",
                overall_risk: "high",
                comment_body:
                  "Owned thread with aging pressure that is not overdue yet.",
                assigned_to_name: "Ada Lovelace",
                assigned_to_email: "ada@example.com",
                is_mine: true,
                is_unassigned: false,
                is_overdue: false,
                overdue_label: null,
                is_escalated: false,
                escalated_at: null,
                queue_age_hours: 44,
                last_activity_at: "2026-04-17T14:30:00Z",
                updated_at: "2026-04-17T14:30:00Z",
                comment_count: 2,
              },
            ],
            updated_at: "2026-04-18T11:45:00Z",
          },
        };

        return {
          data: queueByFilter[filter] ?? queueByFilter.mine,
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    renderPanel();

    expect(screen.getByText("Assigned to you")).toBeInTheDocument();
    expect(screen.getByText("2 assigned to you")).toBeInTheDocument();
    expect(screen.getByText("0 my overdue")).toBeInTheDocument();
    expect(screen.getAllByText("1 at risk next")).toHaveLength(2);
    expect(screen.getByText("0 my escalations")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Aging buckets: 0 overdue · 1 at risk next · 0 watch window",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Owned spotlight")).toBeInTheDocument();
    expect(
      screen.getByTestId("legal-review-spotlight-actions"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("At risk next · 44h open")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /View report/i })).toHaveAttribute(
      "href",
      "/analyses/ana-pre-2/report",
    );
    expect(screen.getByText("Open my overdue")).toHaveAttribute(
      "href",
      "/reviews?focus=my-overdue&sort=priority",
    );
  });

  it("routes risk-restricted scientists to report summaries", () => {
    principalState.role = "scientist";
    principalState.riskRatingsRestricted = true;

    renderPanel();

    expect(screen.getByRole("link", { name: "View summary" })).toHaveAttribute(
      "href",
      "/analyses/ana-1/report/summary",
    );
    expect(
      screen.getAllByRole("link", { name: "Open summary" }).length,
    ).toBeGreaterThan(0);
  });

  it("renders nothing when the queue is forbidden", () => {
    mockUseReviewQueue.mockReturnValue({
      data: { forbidden: true },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = renderPanel();

    expect(container.firstChild).toBeNull();
  });
});
