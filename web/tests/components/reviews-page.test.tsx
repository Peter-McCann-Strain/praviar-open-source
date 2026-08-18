import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseAuthToken = vi.fn();
const mockUseReviewQueue = vi.fn();
const mockUseSearchParams = vi.fn();
const mockRouterReplace = vi.fn();
const principalState = vi.hoisted(() => ({
  available: true,
  canViewReviewQueue: true,
  refetch: vi.fn(),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: principalState.available
      ? {
          can_view_review_queue: principalState.canViewReviewQueue,
        }
      : undefined,
    isFetching: false,
    isLoading: false,
    refetch: principalState.refetch,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockRouterReplace }),
  usePathname: () => "/reviews",
  useSearchParams: () => mockUseSearchParams(),
}));

vi.mock("@/hooks/use-review-queue", () => ({
  useReviewQueue: (...args: unknown[]) => mockUseReviewQueue(...args),
}));

vi.mock("@/components/reviews/review-queue-item-card", () => ({
  ReviewQueueItemCard: () => <div data-testid="review-queue-item-card" />,
}));

vi.mock("@/components/reviews/review-queue-bulk-toolbar", () => ({
  ReviewQueueBulkToolbar: () => null,
}));

import ReviewsPage from "@/app/(dashboard)/reviews/page";

describe("ReviewsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("tok");
    principalState.available = true;
    principalState.canViewReviewQueue = true;
    principalState.refetch.mockReset();
    mockUseSearchParams.mockReturnValue(new URLSearchParams());
    mockUseReviewQueue.mockReturnValue({
      data: {
        counts: {
          total: 2,
          mine: 1,
          unassigned: 1,
          overdue: 0,
          escalated: 1,
        },
        items: [
          {
            id: "rq-1",
            analysis_id: "ana-1",
            compound_name: "Aspirin",
            analysis_status: "completed",
            overall_risk: "high",
            comment_body: "Attorney review requested for the lead claim chart.",
            assigned_to_name: "Ada Lovelace",
            assigned_to_email: "ada@example.com",
            is_mine: true,
            is_unassigned: false,
            is_overdue: false,
            overdue_label: null,
            is_escalated: true,
            escalated_at: "2026-04-18T08:15:00Z",
            last_activity_at: "2026-04-18T10:30:00Z",
            updated_at: "2026-04-18T10:30:00Z",
            comment_count: 3,
          },
        ],
        updated_at: "2026-04-18T10:30:00Z",
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders the dedicated legal review queue page", () => {
    render(<ReviewsPage />);

    expect(screen.getByText("Legal Review Queue")).toBeInTheDocument();
    expect(screen.getByTestId("review-queue-item-card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mine/i })).toBeInTheDocument();
  });

  it("distinguishes a failed capability check from a role restriction", () => {
    principalState.available = false;

    render(<ReviewsPage />);

    expect(
      screen.getByRole("heading", {
        name: "Review access check unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "Review queue access restricted",
      }),
    ).not.toBeInTheDocument();
  });

  it("honors filter and sort params when opening the queue", () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("filter=overdue&sort=compound"),
    );

    render(<ReviewsPage />);

    expect(mockUseReviewQueue).toHaveBeenCalledWith("tok", "overdue");
    expect(screen.getByLabelText("Queue ordering")).toHaveValue("compound");
  });

  it("honors direct reviewer-scope deep links without requiring a focus preset", () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("filter=escalated&sort=priority&scope=mine"),
    );

    render(<ReviewsPage />);

    expect(mockUseReviewQueue).toHaveBeenCalledWith("tok", "escalated");
    expect(screen.getAllByText("Assigned to you").length).toBeGreaterThan(0);
    expect(screen.getByText("My escalated threads")).toBeInTheDocument();
  });

  it("supports focus-driven reviewer queue deep links", () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("focus=my-overdue&sort=priority"),
    );

    render(<ReviewsPage />);

    expect(mockUseReviewQueue).toHaveBeenCalledWith("tok", "overdue");
    expect(screen.getAllByText("Assigned to you").length).toBeGreaterThan(0);
    expect(screen.getByText("My overdue threads")).toBeInTheDocument();
  });

  it("preserves explicit filter and sort when a reviewer focus preset is present", () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("filter=escalated&sort=compound&focus=my-overdue"),
    );

    render(<ReviewsPage />);

    expect(mockUseReviewQueue).toHaveBeenCalledWith("tok", "escalated");
    expect(screen.getByLabelText("Queue ordering")).toHaveValue("compound");
    expect(screen.getAllByText("Assigned to you").length).toBeGreaterThan(0);
    expect(screen.getByText("My escalated threads")).toBeInTheDocument();
  });

  it("lets an explicit reviewer scope override the focus preset", () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("filter=overdue&focus=my-overdue&scope=all"),
    );

    render(<ReviewsPage />);

    expect(mockUseReviewQueue).toHaveBeenCalledWith("tok", "overdue");
    expect(
      screen.queryByRole("group", { name: /Org threads:/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("My overdue threads")).not.toBeInTheDocument();
    expect(screen.getByText("Past SLA threads")).toBeInTheDocument();
  });

  it("shows a quiet access message for forbidden users", () => {
    mockUseReviewQueue.mockReturnValue({
      data: { forbidden: true },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ReviewsPage />);

    expect(
      screen.getByText(/available to internal scientific and legal reviewers/i),
    ).toBeInTheDocument();
  });

  it("preflights direct-link access before mounting the protected queue", () => {
    principalState.canViewReviewQueue = false;

    render(<ReviewsPage />);

    expect(
      screen.getByRole("heading", {
        name: "Review queue access restricted",
      }),
    ).toBeInTheDocument();
    expect(mockUseReviewQueue).not.toHaveBeenCalled();
  });
});
