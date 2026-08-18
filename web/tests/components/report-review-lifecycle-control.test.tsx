import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportReviewLifecycleControl } from "@/components/report-page/report-review-lifecycle-control";
import { APIError } from "@/lib/api-client";

const mockUseUpdateReviewStatus = vi.fn();

vi.mock("@/hooks/use-analysis-review-status", async () => {
  const actual = await vi.importActual<
    typeof import("@/hooks/use-analysis-review-status")
  >("@/hooks/use-analysis-review-status");

  return {
    ...actual,
    useUpdateAnalysisReviewStatus: (...args: unknown[]) =>
      mockUseUpdateReviewStatus(...args),
  };
});

const STATUS = {
  analysis_id: "analysis-1",
  status: "under_review" as const,
  note: "Counsel review started.",
  reviewer_name: "Ada Counsel",
  reviewer_email: "ada@example.test",
  reviewed_at: "2026-07-16T10:00:00.000Z",
  updated_at: "2026-07-16T10:00:00.000Z",
  decision_counts: { accept: 2, reject: 0, edit: 1 },
  findings_total: 4,
  findings_reviewed: 3,
  completion_pct: 75,
};

describe("ReportReviewLifecycleControl", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUpdateReviewStatus.mockReturnValue({
      error: null,
      isPending: false,
      mutateAsync: vi.fn(),
      reset: vi.fn(),
    });
  });

  it("shows authoritative status, finding coverage, and transition consequences", () => {
    render(
      <ReportReviewLifecycleControl
        analysisId="analysis-1"
        status={STATUS}
        onRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Counsel review decision" }),
    ).toBeInTheDocument();
    expect(screen.getByText("3 / 4 reviewed")).toBeInTheDocument();
    expect(screen.getByText("Ada Counsel")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /under review/i })).toBeChecked();
    expect(
      screen.getAllByText(/export remains blocked until approval/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/approval is not a legal opinion/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Record under review" }),
    ).toBeDisabled();
  });

  it("records an approval with an audit note, refreshes, and confirms success", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const mutateAsync = vi.fn().mockResolvedValue({
      ...STATUS,
      status: "approved",
      note: "All material findings reviewed.",
      findings_reviewed: 4,
      completion_pct: 100,
    });
    mockUseUpdateReviewStatus.mockReturnValue({
      error: null,
      isPending: false,
      mutateAsync,
      reset: vi.fn(),
    });

    render(
      <ReportReviewLifecycleControl
        analysisId="analysis-1"
        status={STATUS}
        onRefresh={onRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: /approved/i }));
    fireEvent.change(screen.getByLabelText("Audit note"), {
      target: { value: "All material findings reviewed." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record approved" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        status: "approved",
        note: "All material findings reviewed.",
      });
    });
    await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toHaveTextContent(
      "Approved recorded in the governed review ledger.",
    );
  });

  it("locks the form and announces a pending governed mutation", () => {
    mockUseUpdateReviewStatus.mockReturnValue({
      error: null,
      isPending: true,
      mutateAsync: vi.fn(),
      reset: vi.fn(),
    });

    render(
      <ReportReviewLifecycleControl
        analysisId="analysis-1"
        status={STATUS}
        onRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("form", { name: "Counsel review decision" }),
    ).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByTestId("report-review-lifecycle-control"),
    ).toHaveAttribute("data-no-print");
    expect(
      screen.getByRole("button", { name: "Recording decision" }),
    ).toBeDisabled();
    expect(screen.getByRole("radio", { name: /under review/i })).toBeDisabled();
  });

  it("keeps approval unconfirmed and offers recovery when status cannot load", () => {
    const onRefresh = vi.fn();

    render(
      <ReportReviewLifecycleControl
        analysisId="analysis-1"
        statusError
        onRefresh={onRefresh}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Governed review status unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/export approval must remain unconfirmed/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("explains backend readiness conflicts without exposing raw diagnostics", () => {
    mockUseUpdateReviewStatus.mockReturnValue({
      error: new APIError(409, "The request conflicts with the current state."),
      isPending: false,
      mutateAsync: vi.fn(),
      reset: vi.fn(),
    });

    render(
      <ReportReviewLifecycleControl
        analysisId="analysis-1"
        status={STATUS}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "one or more governed readiness gates still fail",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "The request conflicts with the current state",
    );
  });
});
