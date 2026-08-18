import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  AnalysisCompleteCard,
  CancelledAnalysisCard,
  FailedAnalysisCard,
  PipelineErrorCard,
  PIPELINE_ERROR_SAFE_MESSAGE,
  ReviewPauseCard,
} from "@/components/analysis-detail/analysis-status-cards";

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: true,
    },
  }),
}));

describe("AnalysisCompleteCard", () => {
  it("renders meaningful legal review metadata when present", () => {
    render(
      <AnalysisCompleteCard
        id="ana-1"
        currentUserRole="attorney"
        reviewStatus={{
          status: "approved",
          is_persisted: true,
          reviewer_name: "Ada Lovelace",
          reviewed_at: "2026-04-18T12:00:00Z",
          updated_at: "2026-04-18T12:00:00Z",
        }}
      />,
    );

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/Ada Lovelace/i)).toBeInTheDocument();
  });

  it("hides pending legal review metadata on the completed card", () => {
    render(
      <AnalysisCompleteCard
        id="ana-2"
        currentUserRole="attorney"
        reviewStatus={{
          status: "pending",
          is_persisted: false,
          updated_at: "2026-04-18T12:00:00Z",
        }}
      />,
    );

    expect(screen.queryByText("Approved")).not.toBeInTheDocument();
    expect(screen.queryByText(/Under legal review/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/View the full interactive report/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Open Report Workspace/i }),
    ).toHaveAttribute("href", "/analyses/ana-2/report");
    expect(
      screen.getByRole("link", { name: /Open Report Workspace/i }),
    ).toHaveClass("min-h-11", "w-full", "sm:w-auto", "lg:w-full");
    expect(
      screen.getByRole("link", { name: /Open Report Workspace/i }),
    ).not.toHaveClass("sm:min-h-9");
    expect(screen.getByText("Open report")).toHaveClass("sm:hidden");
    expect(screen.getByText("Open Report Workspace")).toHaveClass(
      "hidden",
      "sm:inline",
    );
    expect(
      screen.queryByRole("link", { name: "Summary" }),
    ).not.toBeInTheDocument();
  });

  it("routes scientist users to the authorized summary", () => {
    render(
      <AnalysisCompleteCard id="ana-scientist" currentUserRole="scientist" />,
    );

    expect(
      screen.getByRole("link", { name: /Open Authorized Summary/i }),
    ).toHaveAttribute("href", "/analyses/ana-scientist/report/summary");
    expect(
      screen.getByText(/View the authorized executive summary/i),
    ).toBeInTheDocument();
  });

  it("routes scientists to the full report when the workspace risk gate permits it", () => {
    render(
      <AnalysisCompleteCard
        id="ana-scientist-open"
        currentUserRole="scientist"
        riskRatingsRestricted={false}
      />,
    );

    expect(
      screen.getByRole("link", { name: /Open Report Workspace/i }),
    ).toHaveAttribute("href", "/analyses/ana-scientist-open/report");
    expect(
      screen.getByText(/View the full interactive report/i),
    ).toBeInTheDocument();
  });
});

describe("analysis status cards", () => {
  it("announces pipeline errors and failed analyses as alerts", () => {
    render(
      <PipelineErrorCard error="postgres://secret-token stack trace SELECT *" />,
    );
    const alert = screen.getByRole("alert");

    expect(alert).toHaveTextContent("Pipeline Error");
    expect(alert).toHaveTextContent(PIPELINE_ERROR_SAFE_MESSAGE);
    expect(alert).toHaveAttribute("data-has-diagnostic-detail", "true");
    expect(
      screen.queryByText(/postgres:\/\/secret-token/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT \*/i)).not.toBeInTheDocument();
  });

  it("renders failed step fallback safely when the backend reports step zero", () => {
    render(<FailedAnalysisCard currentStep={0} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Analysis failed");
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
    expect(screen.getByText("Evidence preserved")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toHaveTextContent("Preserve the last successful evidence");
    expect(screen.getByText("No legal conclusion changed")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Return to analysis library/i }),
    ).toHaveAttribute("href", "/analyses");
    expect(
      screen.getByRole("link", { name: /Start replacement analysis/i }),
    ).toHaveAttribute("href", "/analyses/new");
  });

  it("renders review checkpoints as a paused status rather than an error", () => {
    render(
      <ReviewPauseCard
        checkpoint={{
          checkpoint_type: "analysis_review",
          context: {},
          requires_response: true,
          timeout_minutes: 60,
          step: 4,
          step_name: "analysis_review",
          timestamp: "2026-06-06T00:00:00Z",
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Human review checkpoint",
    );
    expect(screen.queryByText(/Pipeline Error/i)).not.toBeInTheDocument();
  });

  it("renders cancelled analyses as a stable terminal state", () => {
    render(<CancelledAnalysisCard />);
    expect(screen.getByText("Analysis cancelled")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New analysis/i })).toHaveAttribute(
      "href",
      "/analyses/new",
    );
  });
});
