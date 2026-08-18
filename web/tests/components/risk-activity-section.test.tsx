import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskActivitySection } from "@/components/dashboard/risk-activity-section";
import type { DashboardPriorityDocketItem } from "@/components/dashboard/helpers";
import type { AnalysisListItem } from "@/types/api";

function analysisFixture(
  overrides: Partial<AnalysisListItem> = {},
): AnalysisListItem {
  return {
    id: "ana-1",
    compound_input: "aspirin",
    compound_name: "Aspirin",
    compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: "high",
    blocking_patents_count: 2,
    total_patents_found: 15,
    executive_summary: "Blocking composition claims remain active.",
    estimated_cost_usd: 12,
    pipeline_duration_seconds: 320,
    flagged_for_review: true,
    current_user_role: "attorney",
    created_at: "2026-04-17T12:00:00Z",
    updated_at: "2026-04-18T12:00:00Z",
    ...overrides,
  };
}

function renderSection({
  priorityDocket,
  recentAnalyses,
  riskRatingsRestricted = false,
}: {
  priorityDocket: DashboardPriorityDocketItem[];
  recentAnalyses: AnalysisListItem[];
  riskRatingsRestricted?: boolean;
}) {
  return render(
    <RiskActivitySection
      priorityDocket={priorityDocket}
      recentAnalyses={recentAnalyses}
      riskRatingsRestricted={riskRatingsRestricted}
      sampleWindowSize={100}
      riskDistribution={[
        { level: "high", count: 1 },
        { level: "medium", count: 1 },
        { level: "low", count: 0 },
      ]}
    />,
  );
}

describe("RiskActivitySection", () => {
  it("defaults to the scoped action docket with reason chips and review state", () => {
    const aspirin = analysisFixture({
      review_status: {
        status: "under_review",
        is_persisted: true,
        reviewer_name: "Ada Lovelace",
        reviewed_at: "2026-04-18T12:00:00Z",
        updated_at: "2026-04-18T12:00:00Z",
      },
    });

    renderSection({
      priorityDocket: [
        {
          analysis: aspirin,
          reason: "2 blocking patents",
          reasonTone: "critical",
        },
      ],
      recentAnalyses: [aspirin],
    });

    expect(screen.getByText("Action docket")).toBeInTheDocument();
    expect(screen.getByText(/latest 100 analyses/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Action" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Action" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Action" })).not.toHaveClass(
      "min-h-9",
    );
    expect(screen.getByRole("button", { name: "Recent" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByText("2 classified analyses")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Risk distribution chart" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/2 analyses: 1 high, 1 medium, 0 low\./),
    ).toHaveClass("sr-only");
    expect(screen.getByText("Under review")).toBeInTheDocument();
    expect(screen.getByText("2 blocking patents")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Aspirin/i })).toHaveClass(
      "border-l-error",
    );
    expect(screen.getByText("Aspirin")).toHaveAttribute("title", "Aspirin");
  });

  it("switches to recent mode and preserves newest-first ordering", () => {
    const urgentOlder = analysisFixture({
      id: "ana-urgent",
      compound_name: "Oldacin Plus",
      updated_at: "2026-04-17T12:00:00Z",
      review_status: {
        status: "changes_requested",
        is_persisted: true,
        updated_at: "2026-04-17T12:00:00Z",
      },
    });
    const newestShared = analysisFixture({
      id: "ana-new",
      compound_name: "Stride Vector A",
      overall_risk: "low",
      blocking_patents_count: 0,
      flagged_for_review: false,
      share_active: true,
      share_view_count: 4,
      updated_at: "2026-04-19T12:00:00Z",
    });

    renderSection({
      priorityDocket: [
        {
          analysis: urgentOlder,
          reason: "Changes requested",
          reasonTone: "critical",
        },
        {
          analysis: newestShared,
          reason: "Shared with 4 views",
          reasonTone: "info",
        },
      ],
      recentAnalyses: [newestShared, urgentOlder],
    });

    const actionList = screen.getByRole("list", {
      name: "Action docket analyses",
    });
    expect(within(actionList).getAllByRole("link")[0]).toHaveAttribute(
      "href",
      "/analyses/ana-urgent/report?tab=patents",
    );

    fireEvent.click(screen.getByRole("button", { name: "Recent" }));

    expect(screen.getByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recent" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const recentList = screen.getByRole("list", {
      name: "Recent activity analyses",
    });
    expect(within(recentList).getAllByRole("link")[0]).toHaveAttribute(
      "href",
      "/analyses/ana-new/report",
    );
    expect(screen.getByText("Shared with 4 views")).toBeInTheDocument();
  });

  it("keeps in-progress activity linked to the live run workspace", () => {
    const running = analysisFixture({
      id: "ana-running",
      compound_name: "Ibuprofen",
      status: "running",
      current_step: 4,
      progress_pct: 52,
      overall_risk: null,
      blocking_patents_count: 0,
      flagged_for_review: false,
    });

    renderSection({
      priorityDocket: [
        {
          analysis: running,
          reason: "Running step 4/8",
          reasonTone: "info",
        },
      ],
      recentAnalyses: [running],
    });

    expect(screen.getByRole("link", { name: /Ibuprofen/i })).toHaveAttribute(
      "href",
      "/analyses/ana-running",
    );
  });

  it("suppresses pending legal review state and uses pending-specific copy", () => {
    const pending = analysisFixture({
      id: "ana-pending",
      compound_name: "Queued Compound",
      status: "pending",
      overall_risk: null,
      blocking_patents_count: 0,
      flagged_for_review: false,
      executive_summary: "",
      current_step: 1,
      progress_pct: 0,
      review_status: {
        status: "pending",
        is_persisted: false,
        updated_at: "2026-04-18T12:00:00Z",
      },
    });

    renderSection({
      priorityDocket: [
        {
          analysis: pending,
          reason: "Pending launch",
          reasonTone: "neutral",
        },
      ],
      recentAnalyses: [pending],
    });

    expect(screen.queryByText("Under review")).not.toBeInTheDocument();
    expect(screen.queryByText("Approved")).not.toBeInTheDocument();
    expect(screen.getByText("Pending launch")).toBeInTheDocument();
    expect(
      screen.getByText(/queued and will begin evidence collection/i),
    ).toBeInTheDocument();
  });

  it("replaces redacted risk distribution with an explicit counsel boundary", () => {
    const restricted = analysisFixture({
      overall_risk: "high",
      blocking_patents_count: 8,
      risk_ratings_restricted: true,
      current_user_role: "client",
    });

    renderSection({
      priorityDocket: [],
      recentAnalyses: [restricted],
      riskRatingsRestricted: true,
    });

    expect(screen.getByText("Counsel-only risk posture")).toBeInTheDocument();
    expect(screen.getByText("No zero-risk inference")).toBeInTheDocument();
    expect(
      screen.queryByRole("img", { name: "Risk distribution chart" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Counsel only").length).toBeGreaterThan(0);
    expect(screen.queryByText("8 blocking patents")).not.toBeInTheDocument();
    expect(screen.queryByText("High")).not.toBeInTheDocument();
    expect(screen.getByText("Recent movement")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Aspirin/i })).toHaveClass(
      "border-l-warning",
    );
    expect(screen.getByRole("link", { name: /Aspirin/i })).toHaveAttribute(
      "href",
      "/analyses/ana-1/report/summary",
    );
  });

  it("keeps incomplete restricted rows status-aware instead of calling them counsel-only", () => {
    const running = analysisFixture({
      id: "ana-running-restricted",
      compound_name: "Running compound",
      status: "running",
      overall_risk: "high",
      blocking_patents_count: 4,
      risk_ratings_restricted: true,
      current_user_role: "scientist",
    });

    renderSection({
      priorityDocket: [],
      recentAnalyses: [running],
      riskRatingsRestricted: true,
    });

    expect(screen.getByText("Pending classification")).toBeInTheDocument();
    expect(screen.queryAllByText("Counsel only")).toHaveLength(0);
  });
});
