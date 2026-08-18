import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { FTOReport, PatentAnalysis } from "@praviar/shared-types";

vi.mock("@/components/charts/risk-donut", () => ({
  RiskDonut: ({ data }: any) => (
    <div data-testid="risk-donut">
      {data.map((entry: any) => (
        <span key={entry.level}>
          {entry.level}:{entry.count}
        </span>
      ))}
    </div>
  ),
}));

vi.mock("@/components/patent/patent-risk-card", () => ({
  PatentRiskCard: ({ analysis, narrative, defaultExpanded }: any) => (
    <div
      data-testid={`patent-card-${analysis.patent_id}`}
      data-expanded={defaultExpanded ? "true" : "false"}
    >
      {analysis.patent_id}
      {narrative ? <span>{narrative}</span> : null}
    </div>
  ),
}));

vi.mock("@/components/report/review-status-badge", () => ({
  ReviewStatusBadge: ({ status }: any) => <span>{status}</span>,
}));

vi.mock("@/stores/review-store", () => ({
  useReviewStore: () => ({
    getReview: (analysisId: string, patentId: string) =>
      analysisId === "analysis-123" && patentId === "US0000000001A1"
        ? { status: "reviewed" }
        : undefined,
  }),
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

// No server-side reviewer decision in this fixture, so the row should fall back
// to the local review store status.
vi.mock("@/hooks/use-reviewer-decisions", () => ({
  useReviewerDecisions: () => ({ data: undefined }),
}));

import {
  PatentsAccessRestricted,
  PatentsCardList,
  PatentsTabSummary,
  PatentsViewModeToggle,
} from "@/components/report/patents-tab-sections";

function makePatentAnalysis(
  overrides: Partial<PatentAnalysis> = {},
): PatentAnalysis {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process",
    assignee: "Fictional Meridian Therapeutics",
    expiry_date: "2038-01-15",
    claims_analyzed: [
      {
        claim_number: 1,
        claim_type: "independent",
        depends_on: null,
        preamble: "",
        transitional_phrase: "",
        elements: [],
        overall_status: "met",
        overall_confidence: 0.9,
        reasoning: "",
      },
    ],
    risk_level: "high",
    risk_summary: "High risk",
    design_around_suggestions: [],
    orange_book_info: null,
    model_used: "claude-3-opus",
    thinking_text: "",
    input_tokens: 50000,
    output_tokens: 3000,
    ...overrides,
  };
}

function makeReport(overrides: Partial<FTOReport> = {}): FTOReport {
  return {
    report_id: "rpt-001",
    generated_at: "2026-03-12T10:00:00Z",
    praviar_pipeline_version: "0.9.0",
    compound: {
      name: "Succinic acid",
      canonical_smiles: "OC(=O)CCC(O)=O",
      inchi: "InChI=1S/C4H6O4",
      inchi_key: "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
      pubchem_cid: 1110,
      synonyms: [],
      cas_numbers: [],
      molecular_formula: "C4H6O4",
      molecular_weight: 118.09,
      morgan_fp: "",
      maccs_keys: "",
      functional_groups: [],
      related_compounds: [],
      original_input: "succinic acid",
      input_type: "name",
    },
    risk_summary: {
      overall_risk: "medium",
      blocking_patents_count: 1,
      total_patents_analyzed: 2,
      key_risks: [],
      executive_summary: "",
      summary_validation_issues: [],
    },
    patent_analyses: [
      makePatentAnalysis({ patent_id: "US0000000001A1", risk_level: "high" }),
      makePatentAnalysis({
        patent_id: "EP9988776A1",
        risk_level: "medium",
        assignee: "Fictional Atlas Chemistry",
        expiry_date: null,
      }),
    ],
    doe_assessments: [],
    invalidity_assessments: [],
    verification: {
      checks: [],
      all_citations_valid: true,
      all_claims_grounded: true,
      all_entities_valid: true,
      dates_consistent: true,
      risk_levels_justified: true,
      issues: [],
    },
    analysis_failures: [],
    data_limitations: [],
    total_patents_found: 200,
    patents_after_triage: 15,
    search_sources_used: [],
    source_health: { entries: [] },
    scholarly_prior_art_count: 5,
    audit_trail: {
      search_funnel: [
        {
          patent_id: "US0000000001A1",
          family_broadest: true,
        },
      ],
      triage_audit: [],
      analysis_audit: [],
      timing_data: [],
      total_patents_discovered: 200,
      patents_after_hard_filter: 150,
      patents_after_ranking: 40,
      patents_after_triage: 15,
      patents_analyzed: 2,
    },
    patent_narratives: {
      US0000000001A1: "This patent poses the highest risk to the compound.",
    },
    disclaimer: "",
    llm_models_used: {},
    total_input_tokens: 200000,
    total_output_tokens: 12000,
    estimated_cost_usd: 8.5,
    step_token_usage: [],
    ...overrides,
  };
}

describe("patents tab section leaves", () => {
  it("renders the access restriction message", () => {
    render(<PatentsAccessRestricted totalPatentsFound={200} />);

    expect(screen.getByText("Access Restricted")).toBeInTheDocument();
    expect(screen.getByText(/200 patents were found/)).toBeInTheDocument();
  });

  it("switches between card and table modes", () => {
    const onChange = vi.fn();

    render(<PatentsViewModeToggle viewMode="cards" onChange={onChange} />);

    const tableView = screen.getByRole("button", { name: "Table view" });
    const cardView = screen.getByRole("button", { name: "Card view" });
    expect(tableView).toHaveClass("h-11", "w-11");
    expect(cardView).toHaveClass("h-11", "w-11");
    fireEvent.click(tableView);
    expect(onChange).toHaveBeenCalledWith("table");
    fireEvent.click(cardView);
    expect(onChange).toHaveBeenCalledWith("cards");
  });

  it("renders the summary table with broadest badges and review state", () => {
    const report = makeReport();

    render(
      <PatentsTabSummary
        report={report}
        riskData={[
          { level: "HIGH", count: 1 },
          { level: "MEDIUM", count: 1 },
        ]}
        sortedAnalyses={report.patent_analyses}
        analysisId="analysis-123"
        onPatentSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Risk Distribution")).toBeInTheDocument();
    expect(screen.getByTestId("risk-donut")).toHaveTextContent("HIGH:1");
    expect(screen.getByText("Patent Risk Summary")).toBeInTheDocument();
    expect(screen.getByText("Broadest")).toBeInTheDocument();
    expect(
      screen.getByText("This patent poses the highest risk to the compound.…"),
    ).toBeInTheDocument();
    expect(screen.getByText("reviewed")).toBeInTheDocument();
  });

  it("passes narratives and deep-link expansion to the card list", () => {
    const report = makeReport();

    render(
      <PatentsCardList
        sortedAnalyses={report.patent_analyses}
        report={report}
        analysisId="analysis-123"
        deepLinkPatent="EP9988776A1"
        scrollRef={createRef<HTMLDivElement>()}
      />,
    );

    expect(screen.getByTestId("patent-card-US0000000001A1")).toHaveAttribute(
      "data-expanded",
      "false",
    );
    expect(screen.getByTestId("patent-card-EP9988776A1")).toHaveAttribute(
      "data-expanded",
      "true",
    );
    expect(
      screen.getByText("This patent poses the highest risk to the compound."),
    ).toBeInTheDocument();
  });

  it("keeps the card-list show-more action touch-sized", () => {
    const patentAnalyses = Array.from({ length: 52 }, (_, index) =>
      makePatentAnalysis({
        patent_id: `US${String(index + 1).padStart(8, "0")}B2`,
        risk_level: index === 0 ? "high" : "medium",
      }),
    );
    const report = makeReport({ patent_analyses: patentAnalyses });

    render(
      <PatentsCardList
        sortedAnalyses={report.patent_analyses}
        report={report}
        analysisId="analysis-123"
        deepLinkPatent={null}
        scrollRef={createRef<HTMLDivElement>()}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "Show more patents (2 remaining)",
      }),
    ).toHaveClass("min-h-11");
  });
});
