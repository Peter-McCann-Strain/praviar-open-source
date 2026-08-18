import { beforeEach, describe, it, expect, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type {
  FTOReport,
  PatentAnalysis,
  PatentHit,
} from "@praviar/shared-types";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";

// Mock Recharts RiskDonut
vi.mock("@/components/charts/risk-donut", () => ({
  RiskDonut: ({ data }: any) => (
    <div data-testid="risk-donut">
      {data.map((d: any) => (
        <span key={d.level} data-testid={`donut-${d.level.toLowerCase()}`}>
          {d.level}: {d.count}
        </span>
      ))}
    </div>
  ),
}));

// Mock PatentRiskCard
vi.mock("@/components/patent/patent-risk-card", () => ({
  PatentRiskCard: ({ analysis, narrative }: any) => (
    <div data-testid={`patent-card-${analysis.patent_id}`}>
      <span>{analysis.patent_id}</span>
      <span>{analysis.risk_level}</span>
      {narrative && <span data-testid="narrative">{narrative}</span>}
    </div>
  ),
}));

// The risk summary row reads server reviewer decisions (source of truth) via
// these hooks; stub them so the table renders without a QueryClientProvider.
vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "test-token",
}));

vi.mock("@/hooks/use-reviewer-decisions", () => ({
  useReviewerDecisions: () => ({ data: undefined }),
}));

const navigationMocks = vi.hoisted(() => ({
  searchParams: new URLSearchParams(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => navigationMocks.searchParams,
  usePathname: () => "/analyses/analysis-123/report",
}));

import { PatentsTab } from "@/components/report/patents-tab";

// ---------------------------------------------------------------------------
// Test data builders
// ---------------------------------------------------------------------------

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

function makePatentHit(overrides: Partial<PatentHit> = {}): PatentHit {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process",
    abstract: "An improved fermentation process for producing succinic acid.",
    claims_text: "1. A fermentation process for producing succinic acid.",
    sources: [],
    confidence_score: 0.82,
    filing_date: "2018-01-10",
    priority_date: "2017-01-10",
    expiry_date: "2038-01-15",
    assignees: ["Fictional Meridian Therapeutics"],
    inventors: ["Jane Doe"],
    cpc_codes: ["C12P 7/46"],
    legal_status: "active",
    match_type: "similarity",
    tanimoto_score: 0.73,
    is_granted: true,
    legal_events: [],
    family: {
      family_id: "fam-1",
      members: [{ country: "US", doc_number: "11234567", kind: "B2" }],
    },
    patent_term_info: {
      patent_id: "US0000000001A1",
      effective_filing_date: "2018-01-10",
      grant_date: "2020-04-01",
      base_expiry: "2038-01-10",
      pta_days: 5,
      pte_days: 0,
      terminal_disclaimer: false,
      td_linked_patent: "",
      maintenance_fee_status: "paid",
      adjusted_expiry: "2038-01-15",
      calculation_confidence: 0.9,
      calculation_notes: [],
    },
    ...overrides,
  };
}

function makeMockReport(overrides: Partial<FTOReport> = {}): FTOReport {
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
      blocking_patents_count: 2,
      total_patents_analyzed: 4,
      key_risks: [],
      executive_summary: "",
      summary_validation_issues: [],
    },
    patent_analyses: [
      makePatentAnalysis({
        patent_id: "US0000000001A1",
        risk_level: "high",
        assignee: "Fictional Meridian Therapeutics",
        expiry_date: "2038-01-15",
      }),
      makePatentAnalysis({
        patent_id: "US0000000002A1",
        risk_level: "medium",
        assignee: "Fictional Atlas Chemistry",
        expiry_date: "2035-06-20",
      }),
      makePatentAnalysis({
        patent_id: "US0000000003A1",
        risk_level: "low",
        assignee: "Fictional Nova",
        expiry_date: "2032-11-01",
      }),
      makePatentAnalysis({
        patent_id: "US0000000013A1",
        risk_level: "clear",
        assignee: "DSM IP",
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
      search_funnel: [],
      triage_audit: [],
      analysis_audit: [],
      timing_data: [],
      total_patents_discovered: 200,
      patents_after_hard_filter: 150,
      patents_after_ranking: 40,
      patents_after_triage: 15,
      patents_analyzed: 4,
    },
    patent_narratives: {
      US0000000001A1: "This patent poses the highest risk to the compound.",
      US0000000002A1: "Moderate overlap with purification claims.",
    },
    patent_details: {
      US0000000001A1: makePatentHit(),
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

describe("PatentsTab", () => {
  beforeEach(() => {
    navigationMocks.searchParams = new URLSearchParams();
  });

  it("renders Risk Distribution card title", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(screen.getByText("Risk Distribution")).toBeInTheDocument();
  });

  it("renders Patent Risk Summary table title", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(screen.getByText("Patent Risk Summary")).toBeInTheDocument();
  });

  it("passes correct risk distribution data to RiskDonut", () => {
    render(<PatentsTab report={makeMockReport()} />);
    const donut = screen.getByTestId("risk-donut");
    expect(donut).toHaveTextContent("HIGH: 1");
    expect(donut).toHaveTextContent("MEDIUM: 1");
    expect(donut).toHaveTextContent("LOW: 1");
    expect(donut).toHaveTextContent("CLEAR: 1");
  });

  it("renders all patent IDs in the summary table", () => {
    render(<PatentsTab report={makeMockReport()} />);
    // Patent IDs in the table (not the card mock)
    expect(
      screen.getByText("Fictional Meridian Therapeutics"),
    ).toBeInTheDocument();
    expect(screen.getByText("Fictional Atlas Chemistry")).toBeInTheDocument();
    expect(screen.getByText("Fictional Nova")).toBeInTheDocument();
    expect(screen.getByText("DSM IP")).toBeInTheDocument();
  });

  it("renders expiry dates in summary table, with dash for null", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(screen.getByText("2038-01-15")).toBeInTheDocument();
    expect(screen.getByText("2035-06-20")).toBeInTheDocument();
    expect(screen.getByText("2032-11-01")).toBeInTheDocument();
    // null expiry -> em dash
    expect(screen.getByText("\u2014")).toBeInTheDocument();
  });

  it("sorts patents by risk level: high first, clear last", () => {
    const { container } = render(<PatentsTab report={makeMockReport()} />);
    // Get patent card test IDs in order — they should be sorted high > medium > low > clear
    const cards = container.querySelectorAll("[data-testid^='patent-card-']");
    expect(cards).toHaveLength(4);
    expect(cards[0].getAttribute("data-testid")).toBe(
      "patent-card-US0000000001A1",
    );
    expect(cards[1].getAttribute("data-testid")).toBe(
      "patent-card-US0000000002A1",
    );
    expect(cards[2].getAttribute("data-testid")).toBe(
      "patent-card-US0000000003A1",
    );
    expect(cards[3].getAttribute("data-testid")).toBe(
      "patent-card-US0000000013A1",
    );
  });

  it("passes narratives to PatentRiskCard components", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(
      screen.getByText("This patent poses the highest risk to the compound."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Moderate overlap with purification claims."),
    ).toBeInTheDocument();
  });

  it("renders RiskBadge for each patent in the summary table", () => {
    render(<PatentsTab report={makeMockReport()} />);
    // RiskBadge renders risk.toUpperCase() text
    expect(screen.getAllByText("HIGH").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("MEDIUM").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("LOW").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("CLEAR").length).toBeGreaterThanOrEqual(1);
  });

  it("normalizes claim-source-only persisted detail before opening the drawer", async () => {
    navigationMocks.searchParams = new URLSearchParams("patent=US0000000001A1");
    render(
      <PatentsTab
        report={makeMockReport({
          patent_details: {
            US0000000001A1: {
              claims_text: "1. A fermentation process.",
              claims_text_source: "authority_record",
            } as PatentHit,
          },
        })}
      />,
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Patent details for US0000000001A1",
    });
    expect(dialog).toHaveTextContent("Fermentation process");
    expect(dialog).toHaveTextContent("Fictional Meridian Therapeutics");
    expect(
      screen.getByRole("button", { name: "Close patent details" }),
    ).toBeInTheDocument();
  });

  it("renders table column headers", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(screen.getByText("Patent")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
    expect(screen.getByText("Assignee")).toBeInTheDocument();
    expect(screen.getByText("Expiry")).toBeInTheDocument();
  });

  it("surfaces report-level enforceability confidence before patent drilldown", () => {
    render(
      <PatentsTab
        report={makeMockReport({
          patent_details: {
            US0000000001A1: makePatentHit({
              patent_id: "US0000000001A1",
              patent_term_info: {
                patent_id: "US0000000001A1",
                effective_filing_date: "2018-01-10",
                grant_date: "2020-04-01",
                base_expiry: "2038-01-10",
                pta_days: 5,
                pte_days: 0,
                terminal_disclaimer: false,
                td_linked_patent: "",
                maintenance_fee_status: "paid",
                adjusted_expiry: "2038-01-15",
                calculation_confidence: 0.93,
                calculation_notes: [],
              },
            }),
            US0000000002A1: makePatentHit({
              patent_id: "US0000000002A1",
              legal_status: "active",
              family: null,
              patent_term_info: {
                patent_id: "US0000000002A1",
                effective_filing_date: "2016-06-20",
                grant_date: "2019-03-01",
                base_expiry: "2036-06-20",
                pta_days: 0,
                pte_days: 0,
                terminal_disclaimer: false,
                td_linked_patent: "",
                maintenance_fee_status: "grace_period",
                maintenance_fee_next_due: "2026-09-15",
                adjusted_expiry: "2036-06-20",
                calculation_confidence: 0.61,
                calculation_notes: ["Fee status requires register review."],
              },
            }),
          },
        })}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Enforceability confidence" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Register review required")).toBeInTheDocument();
    expect(screen.getByText("2/4 active")).toBeInTheDocument();
    expect(screen.getByText("3 need review")).toBeInTheDocument();
    expect(screen.getByText("1/4 with family")).toBeInTheDocument();
    expect(screen.getByText("77% avg")).toBeInTheDocument();
    expect(screen.getByText("1 calculation below 80%")).toBeInTheDocument();
  });

  it("renders patent summary rows with mobile scan labels", () => {
    render(<PatentsTab report={makeMockReport()} />);
    expect(screen.getAllByText("Risk level")).toHaveLength(4);
    expect(screen.getAllByText("Review status")).toHaveLength(4);
    expect(screen.getAllByText("Owner")).toHaveLength(4);
    expect(screen.getAllByText("Expiration")).toHaveLength(4);
  });

  it("exposes patent summary rows through native buttons", () => {
    render(<PatentsTab report={makeMockReport()} />);
    const patentButton = screen.getByRole("button", {
      name: "Open patent details for US0000000001A1",
    });

    expect(patentButton).toBeInTheDocument();
    expect(patentButton).toHaveClass("min-h-11");
    expect(patentButton).not.toHaveClass("md:min-h-0");
  });

  it("opens the patent detail drawer from a patent URL parameter", async () => {
    navigationMocks.searchParams = new URLSearchParams(
      "tab=patents&patent=US0000000001A1",
    );

    render(<PatentsTab report={makeMockReport()} />);

    expect(
      await screen.findByRole("dialog", {
        name: "Patent details for US0000000001A1",
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("finding-confidence-badge")).toHaveAttribute(
      "data-level",
      "HIGH",
    );
    expect(screen.getByTestId("finding-confidence-badge")).toHaveTextContent(
      "90% · 1/1 claim",
    );
    expect(screen.getByText("Google Patents")).toBeInTheDocument();
  });

  it("opens an analysis-backed drawer when raw patent details are absent", async () => {
    navigationMocks.searchParams = new URLSearchParams(
      "tab=patents&patent=US0000000002A1",
    );

    render(<PatentsTab report={makeMockReport()} />);

    const dialog = await screen.findByRole("dialog", {
      name: "Patent details for US0000000002A1",
    });
    expect(dialog).toHaveTextContent("Fictional Atlas Chemistry");
    expect(dialog).toHaveTextContent("Status not reported");
  });

  it("renders sortable data table headers as native buttons", () => {
    render(<PatentsTab report={makeMockReport()} />);

    fireEvent.click(screen.getByRole("button", { name: "Table view" }));

    const sortButton = screen.getByRole("button", {
      name: "Sort Patent Number ascending",
    });
    const sortHeader = sortButton.closest("th");

    expect(sortHeader).toHaveAttribute("aria-sort", "none");
    fireEvent.click(sortButton);
    expect(sortHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("passes analysisId to PatentRiskCard when provided", () => {
    // This test verifies the prop is passed without error
    const { container } = render(
      <PatentsTab report={makeMockReport()} analysisId="analysis-123" />,
    );
    const cards = container.querySelectorAll("[data-testid^='patent-card-']");
    expect(cards).toHaveLength(4);
  });

  it("clears private patent table search and row selection on auth boundary changes", () => {
    render(<PatentsTab report={makeMockReport()} />);

    fireEvent.click(screen.getByRole("button", { name: "Table view" }));

    const tableSearch = screen.getByLabelText(
      "Search patents by number, title, or assignee...",
    );
    fireEvent.change(tableSearch, { target: { value: "Fictional Meridian" } });
    fireEvent.click(screen.getByLabelText("Select patent US0000000001A1"));

    expect(tableSearch).toHaveValue("Fictional Meridian");
    expect(screen.getByText("Export 1 selected")).toBeInTheDocument();

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });

    expect(
      screen.getByLabelText("Search patents by number, title, or assignee..."),
    ).toHaveValue("");
    expect(screen.getByText("Export all")).toBeInTheDocument();
  });
});
