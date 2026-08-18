import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  reviewerError: null as Error | null,
  reviewers: [] as Array<{
    id: string;
    email: string;
    full_name: string;
    role: string;
    label: string;
  }>,
  resolve: vi.fn(),
}));

vi.mock("@/hooks/use-comments", () => ({
  useCommentReviewers: () => ({
    data: mocks.reviewers,
    error: mocks.reviewerError,
    isLoading: false,
  }),
  useAssignComment: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useEscalateComment: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useToggleCommentResolution: () => ({
    isPending: false,
    mutateAsync: mocks.resolve,
  }),
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

import { LegalReviewSpotlightActions } from "@/components/dashboard/legal-review-spotlight-actions";
import {
  buildReviewQueueActionError,
  REVIEWER_LIST_ERROR_COPY,
} from "@/components/reviews/review-queue-errors";
import type { ReviewQueueItem } from "@/hooks/use-review-queue";

const item: ReviewQueueItem = {
  id: "rq-1",
  analysis_id: "ana-1",
  compound_name: "Aspirin",
  analysis_status: "completed",
  overall_risk: "high",
  comment_body: "Attorney review requested.",
  assigned_to_id: "reviewer-1",
  assigned_to_name: "Ada Lovelace",
  assigned_to_email: "ada@example.com",
  is_mine: true,
  is_unassigned: false,
  is_overdue: true,
  overdue_label: "Overdue",
  is_escalated: false,
  escalated_at: null,
  queue_age_hours: 52,
  last_activity_at: "2026-04-18T10:30:00Z",
  updated_at: "2026-04-18T10:30:00Z",
  comment_count: 3,
};

describe("LegalReviewSpotlightActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.reviewerError = null;
    mocks.reviewers = [];
    principalState.canAssign = true;
    principalState.canResolve = true;
    principalState.canEscalate = true;
  });

  it("keeps owner selects and review actions touch sized across modes", () => {
    const { rerender } = render(
      <LegalReviewSpotlightActions
        item={item}
        token="tok"
        onQueueRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("combobox", {
        name: "Assign owner for Aspirin from spotlight",
      }),
    ).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Assign owner" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Resolve thread" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Escalate" })).toHaveClass(
      "min-h-11",
    );

    rerender(
      <LegalReviewSpotlightActions
        item={item}
        token="tok"
        mode="inline"
        onQueueRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("combobox", {
        name: "Assign owner for Aspirin from inline tray",
      }),
    ).toHaveClass("min-h-11");
    expect(screen.getByRole("button", { name: "Assign" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Resolve" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Escalate" })).toHaveClass(
      "min-h-11",
    );
  });

  it("wraps long owner and selected reviewer labels", () => {
    const longReviewer =
      "external.counsel.with.long.markush.and-continuation-review-identity@crossborder-diligence.example";
    mocks.reviewers = [
      {
        id: "reviewer-long",
        email: longReviewer,
        full_name: "",
        role: "attorney",
        label: longReviewer,
      },
    ];

    render(
      <LegalReviewSpotlightActions
        item={{
          ...item,
          assigned_to_id: "reviewer-long",
          assigned_to_name: null,
          assigned_to_email: longReviewer,
        }}
        token="tok"
        onQueueRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("combobox", {
        name: "Assign owner for Aspirin from spotlight",
      }),
    ).toHaveClass("max-w-full");
    expect(screen.getByText(`Current owner: ${longReviewer}`)).toHaveClass(
      "min-w-0",
      "max-w-full",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(`Selected: ${longReviewer}`)).toHaveClass(
      "min-w-0",
      "max-w-full",
      "[overflow-wrap:anywhere]",
    );
  });

  it("announces failed dashboard review actions", async () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mocks.resolve.mockRejectedValueOnce(
      new Error("postgres://secret-host reviewer mutation failed"),
    );

    render(
      <LegalReviewSpotlightActions
        item={item}
        token="tok"
        onQueueRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Resolve thread" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      buildReviewQueueActionError("resolve"),
    );
    expect(
      screen.queryByText(/postgres:\/\/secret-host|mutation failed/i),
    ).not.toBeInTheDocument();
    const loggedText = consoleErrorSpy.mock.calls.flat().join(" ");
    expect(loggedText).not.toContain("postgres://secret-host");
    consoleErrorSpy.mockRestore();
  });

  it("shows safe reviewer-list copy instead of raw backend messages", () => {
    mocks.reviewerError = new Error(
      "SELECT * FROM reviewers using postgres://secret",
    );

    render(
      <LegalReviewSpotlightActions
        item={item}
        token="tok"
        onQueueRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText(REVIEWER_LIST_ERROR_COPY)).toBeInTheDocument();
    expect(
      screen.queryByText(/SELECT \* FROM reviewers|postgres:\/\/secret/i),
    ).not.toBeInTheDocument();
  });
});
