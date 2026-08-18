import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewerDecisionButton } from "@/components/report/reviewer-decision-button";

vi.mock("@/hooks/use-reviewer-decisions", () => ({
  useReviewerDecisions: () => ({
    data: {
      counts: { accept: 1, edit: 1, reject: 0 },
    },
  }),
}));

vi.mock("@/components/report/reviewer-decision-panel", () => ({
  ReviewerDecisionPanel: () => (
    <div data-testid="reviewer-decision-panel">Reviewer decision panel</div>
  ),
}));

const REVIEW_STATUS = {
  analysis_id: "analysis-1",
  status: "under_review",
  note: "Counsel review in progress.",
  reviewer_name: "Demo Counsel",
  reviewer_email: "counsel@example.test",
  reviewed_at: null,
  updated_at: "2026-04-24T10:00:00.000Z",
  decision_counts: { accept: 1, reject: 0, edit: 1 },
  findings_total: 4,
  findings_reviewed: 2,
  completion_pct: 50,
} as const;

describe("ReviewerDecisionButton", () => {
  it("runs the pre-open callback before rendering the decision panel", () => {
    const onBeforeOpen = vi.fn();

    render(
      <ReviewerDecisionButton
        analysisId="analysis-1"
        token="tok"
        report={{}}
        onBeforeOpen={onBeforeOpen}
      />,
    );

    fireEvent.click(screen.getByTestId("reviewer-decision-button"));

    expect(onBeforeOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("reviewer-decision-panel")).toBeInTheDocument();
  });

  it("prioritizes the shared reliance ledger over raw decision counts", () => {
    render(
      <ReviewerDecisionButton
        analysisId="analysis-1"
        token="tok"
        report={{}}
        reviewStatus={REVIEW_STATUS}
      />,
    );

    const button = screen.getByTestId("reviewer-decision-button");
    expect(button).toHaveTextContent("Ledger · 2/4");
    expect(button).toHaveAttribute(
      "title",
      "2 / 4 findings reviewed; 1 accepted / 1 edited",
    );
  });
});
