import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  AiCommandPanel,
  buildAiCommandActions,
} from "@/components/dashboard/ai-command-panel";
import type { AnalysisListItem } from "@/types/api";

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  canAccessWorkspaceHref: () => true,
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: true,
    },
  }),
}));

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
    total_patents_found: 42,
    executive_summary: "Blocking composition claims remain active.",
    estimated_cost_usd: 10,
    pipeline_duration_seconds: 180,
    flagged_for_review: true,
    current_user_role: "attorney",
    created_at: "2026-06-18T10:00:00Z",
    updated_at: "2026-06-18T10:30:00Z",
    ...overrides,
  };
}

describe("AiCommandPanel", () => {
  it("prioritizes blocking-patent, reviewer, and running-analysis actions", () => {
    const actions = buildAiCommandActions([
      analysisFixture({
        id: "ana-high",
        compound_name: "Succinic acid",
        blocking_patents_count: 3,
        flagged_for_review: false,
      }),
      analysisFixture({
        id: "ana-review",
        compound_name: "Aspirin",
        overall_risk: "medium",
        blocking_patents_count: 0,
        review_status: {
          status: "changes_requested",
          is_persisted: true,
          updated_at: "2026-06-19T10:00:00Z",
        },
      }),
      analysisFixture({
        id: "ana-running",
        compound_name: "Ibuprofen",
        status: "running",
        current_step: 4,
        progress_pct: 52,
        overall_risk: null,
        blocking_patents_count: 0,
        flagged_for_review: false,
      }),
    ]);

    expect(actions.map((action) => action.title)).toEqual([
      "Draft blocking-patent brief",
      "Prepare reviewer questions",
      "Monitor adaptive run",
    ]);
    expect(actions[0]?.href).toBe(
      "/analyses/ana-high/report?ai_context=blocker_brief&tab=patents",
    );
    expect(actions[1]?.href).toBe(
      "/analyses/ana-review/report?ai_context=review_questions&tab=evidence",
    );
    expect(actions[1]?.meta).toBe("changes requested");
    expect(actions[2]?.href).toBe("/analyses/ana-running");
  });

  it("renders governed guardrails, operating signals, and action links", () => {
    render(
      <AiCommandPanel
        sampleWindowSize={100}
        analyses={[
          analysisFixture({
            id: "ana-high",
            compound_name: "Succinic acid",
            blocking_patents_count: 3,
            flagged_for_review: false,
          }),
          analysisFixture({
            id: "ana-running",
            compound_name: "Ibuprofen",
            status: "running",
            progress_pct: 52,
            overall_risk: null,
            blocking_patents_count: 0,
            flagged_for_review: false,
          }),
        ]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Evidence-ready next moves" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Grounded in the latest 100 analyses/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Claim-cited output")).toBeInTheDocument();
    expect(screen.getByText("Human review gate")).toBeInTheDocument();
    expect(screen.getByText("Tenant-scoped context")).toBeInTheDocument();
    expect(
      screen.getByRole("group", {
        name: "AI workbench operating signals",
      }),
    ).toBeInTheDocument();

    const panel = screen.getByTestId("dashboard-ai-command-panel");
    expect(panel).toHaveAttribute(
      "data-praviar-ai-workbench",
      "governed-next-actions",
    );
    expect(panel.className).toContain("praviar-surface-premium");
    expect(panel.className).not.toContain("bg-[var(--brand-ink)]");
    expect(screen.getByTestId("dashboard-ai-command-header-grid")).toHaveClass(
      "2xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.54fr)]",
    );
    expect(screen.getByTestId("dashboard-ai-command-body-grid")).toHaveClass(
      "2xl:grid-cols-[minmax(0,1.38fr)_minmax(18rem,0.62fr)]",
    );
    expect(
      screen.getByTestId("dashboard-ai-command-body-grid").className,
    ).not.toContain("lg:grid-cols-[minmax(0,1.38fr)_minmax(18rem,0.62fr)]");
    expect(
      within(panel).getByRole("link", { name: /Draft blocking-patent brief/i }),
    ).toHaveAttribute(
      "href",
      "/analyses/ana-high/report?ai_context=blocker_brief&tab=patents",
    );
    expect(
      within(panel).getByRole("link", { name: /Monitor adaptive run/i }),
    ).toHaveAttribute("href", "/analyses/ana-running");
  });

  it("falls back to a compound preflight action when there are no analyses", () => {
    render(<AiCommandPanel analyses={[]} />);

    expect(screen.getByText("Launch compound preflight")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Start preflight/i }),
    ).toHaveAttribute("href", "/analyses/new");
  });

  it("does not infer zero blockers or expose blocker actions when risk is restricted", () => {
    const restricted = analysisFixture({
      blocking_patents_count: 7,
      overall_risk: "high",
      risk_ratings_restricted: true,
      current_user_role: "client",
      flagged_for_review: false,
    });

    expect(
      buildAiCommandActions([restricted]).map((action) => action.title),
    ).not.toContain("Draft blocking-patent brief");

    render(<AiCommandPanel analyses={[restricted]} />);

    expect(screen.getByText("Counsel only")).toBeInTheDocument();
    expect(screen.getByText("Role-filtered · governed")).toBeInTheDocument();
    expect(screen.queryByText("Blockers")).not.toBeInTheDocument();
    expect(screen.queryByText("High risk")).not.toBeInTheDocument();
    expect(screen.queryByText("7 blockers")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Draft blocking-patent brief/i }),
    ).not.toBeInTheDocument();
  });
});
