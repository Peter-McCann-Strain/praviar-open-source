import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { FTOReport } from "@praviar/shared-types";

import { createMotionMock } from "../helpers/mock-motion";

vi.mock("motion/react", () => createMotionMock());

import { AuditTab } from "@/components/report/audit-tab";

// ---------------------------------------------------------------------------
// Minimal mock FTOReport with realistic audit data
// ---------------------------------------------------------------------------

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
      cas_numbers: ["110-15-6"],
      molecular_formula: "C4H6O4",
      molecular_weight: 118.09,
      morgan_fp: "",
      maccs_keys: "",
      functional_groups: ["carboxylic_acid"],
      related_compounds: [],
      original_input: "succinic acid",
      input_type: "name",
    },
    risk_summary: {
      overall_risk: "medium",
      blocking_patents_count: 2,
      total_patents_analyzed: 5,
      key_risks: ["Process patents"],
      executive_summary: "Medium risk due to process patents",
      summary_validation_issues: [],
    },
    patent_analyses: [
      {
        patent_id: "US0000000001A1",
        title: "Fermentation process",
        assignee: "Fictional Meridian Therapeutics",
        expiry_date: "2038-01-15",
        claims_analyzed: [],
        risk_level: "high",
        risk_summary: "High risk",
        design_around_suggestions: [],
        orange_book_info: null,
        model_used: "claude-3-opus",
        thinking_text:
          "This patent covers a fermentation method that overlaps significantly.",
        input_tokens: 50000,
        output_tokens: 3000,
      },
      {
        patent_id: "US0000000002A1",
        title: "Purification method",
        assignee: "Fictional Atlas Chemistry",
        expiry_date: "2035-06-20",
        claims_analyzed: [],
        risk_level: "medium",
        risk_summary: "Medium risk",
        design_around_suggestions: [],
        orange_book_info: null,
        model_used: "claude-3-opus",
        thinking_text: "",
        input_tokens: 40000,
        output_tokens: 2500,
      },
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
    total_patents_found: 389,
    patents_after_triage: 20,
    search_sources_used: ["pubchem", "bigquery"],
    source_health: { entries: [] },
    scholarly_prior_art_count: 12,
    audit_trail: {
      search_funnel: [
        {
          patent_id: "US0000000001A1",
          sources_found_in: ["pubchem"],
          passed_hard_filter: true,
          filter_reason: "",
          composite_score: 0.85,
          bm25_score: 0.7,
          final_blend_score: 0.8,
          final_rank: 1,
          included_in_triage: true,
        },
        {
          patent_id: "US00000001A1",
          sources_found_in: ["bigquery"],
          passed_hard_filter: false,
          filter_reason: "Expired before filing",
          composite_score: null,
          bm25_score: null,
          final_blend_score: null,
          final_rank: null,
          included_in_triage: false,
        },
        {
          patent_id: "US00000002A1",
          sources_found_in: ["bigquery"],
          passed_hard_filter: false,
          filter_reason: "Expired before filing",
          composite_score: null,
          bm25_score: null,
          final_blend_score: null,
          final_rank: null,
          included_in_triage: false,
        },
        {
          patent_id: "US00000003A1",
          sources_found_in: ["pubchem"],
          passed_hard_filter: false,
          filter_reason: "No claims text",
          composite_score: null,
          bm25_score: null,
          final_blend_score: null,
          final_rank: null,
          included_in_triage: false,
        },
      ],
      triage_audit: [
        {
          patent_id: "US0000000001A1",
          relevance: "relevant",
          reason: "Directly covers succinic acid fermentation process",
          confidence: 0.92,
          passed_triage: true,
        },
        {
          patent_id: "US0000000002A1",
          relevance: "possibly_relevant",
          reason: "Related purification method",
          confidence: 0.65,
          passed_triage: true,
        },
        {
          patent_id: "US55555555A1",
          relevance: "not_relevant",
          reason: "Unrelated chemical process",
          confidence: 0.88,
          passed_triage: false,
        },
      ],
      analysis_audit: [
        {
          patent_id: "US0000000001A1",
          selected_for_analysis: true,
          selection_reason: "High relevance score",
          risk_level: "high",
          selected_for_doe: true,
          selected_for_invalidity: true,
        },
        {
          patent_id: "US0000000002A1",
          selected_for_analysis: true,
          selection_reason: "Possibly relevant",
          risk_level: "medium",
          selected_for_doe: false,
          selected_for_invalidity: false,
        },
      ],
      timing_data: [
        {
          step_name: "resolve",
          started_at: "2026-03-12T10:00:00Z",
          completed_at: "2026-03-12T10:00:05Z",
          duration_seconds: 5,
          items_processed: 1,
          items_output: 1,
        },
        {
          step_name: "search",
          started_at: "2026-03-12T10:00:05Z",
          completed_at: "2026-03-12T10:03:05Z",
          duration_seconds: 180,
          items_processed: 4,
          items_output: 389,
        },
      ],
      total_patents_discovered: 389,
      patents_after_hard_filter: 278,
      patents_after_ranking: 50,
      patents_after_triage: 20,
      patents_analyzed: 5,
    },
    patent_narratives: {},
    disclaimer: "This is a screening tool only.",
    llm_models_used: { analysis: "claude-3-opus" },
    total_input_tokens: 500000,
    total_output_tokens: 30000,
    estimated_cost_usd: 11.17,
    step_token_usage: [],
    ...overrides,
  };
}

describe("AuditTab", () => {
  it("renders the Pipeline Funnel Explorer", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("Pipeline Funnel Explorer")).toBeInTheDocument();
  });

  it("displays funnel stage counts", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("389")).toBeInTheDocument(); // Discovered
    expect(screen.getByText("278")).toBeInTheDocument(); // Hard Filtered
    expect(screen.getByText("5")).toBeInTheDocument(); // Analyzed
  });

  it("renders hard filter rejections table with grouped reasons", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("Hard Filter Rejections")).toBeInTheDocument();
    // 2 patents rejected for "Expired before filing", 1 for "No claims text"
    expect(screen.getByText("Expired before filing")).toBeInTheDocument();
    expect(screen.getByText("No claims text")).toBeInTheDocument();
    // Count column — "Expired before filing" has 2 entries
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders triage decisions table with patent IDs and relevance", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("Pre-analysis Triage")).toBeInTheDocument();
    expect(
      screen.getByText(/screening signals, not final FTO risk/i),
    ).toBeInTheDocument();
    // US0000000001A1 appears in both triage and analysis tables
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByText("US55555555A1")).toBeInTheDocument();
    expect(screen.getByText("relevant")).toBeInTheDocument();
    expect(screen.getByText("possibly relevant")).toBeInTheDocument();
    expect(screen.getByText("not relevant")).toBeInTheDocument();
  });

  it("shows triage confidence as percentage", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("65%")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
  });

  it("renders triage reasons", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(
      screen.getByText("Directly covers succinic acid fermentation process"),
    ).toBeInTheDocument();
    expect(screen.getByText("Related purification method")).toBeInTheDocument();
  });

  it("renders analysis selection table with checkmarks and crosses", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("Candidate Analysis Routing")).toBeInTheDocument();
    expect(
      screen.getByText(/does not mean invalidity was assessed/i),
    ).toBeInTheDocument();
    expect(screen.getByText("High relevance score")).toBeInTheDocument();
    expect(screen.getByText("Possibly relevant")).toBeInTheDocument();
    // Check risk levels displayed
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
  });

  it("renders review-basis section with patents that need explanation", () => {
    render(<AuditTab report={makeMockReport()} />);
    expect(screen.getByText("Review Basis Notes")).toBeInTheDocument();
    // Only US0000000001A1 has non-empty thinking_text
    expect(
      screen.getByText(/US0000000001A1 - Review basis note/),
    ).toBeInTheDocument();
  });

  it("expands review-basis panel on click to show note text", () => {
    render(<AuditTab report={makeMockReport()} />);
    const thinkingButton = screen.getByText(
      /US0000000001A1 - Review basis note/,
    );
    fireEvent.click(thinkingButton);
    expect(
      screen.getByText(
        "This patent covers a fermentation method that overlaps significantly.",
      ),
    ).toBeInTheDocument();
  });

  it("does not render hard filter rejections when all patents pass", () => {
    const report = makeMockReport({
      audit_trail: {
        ...makeMockReport().audit_trail,
        search_funnel: [
          {
            patent_id: "US0000000001A1",
            sources_found_in: ["pubchem"],
            passed_hard_filter: true,
            filter_reason: "",
            composite_score: 0.85,
            bm25_score: 0.7,
            final_blend_score: 0.8,
            final_rank: 1,
            included_in_triage: true,
          },
        ],
      },
    });
    render(<AuditTab report={report} />);
    expect(
      screen.queryByText("Hard Filter Rejections"),
    ).not.toBeInTheDocument();
  });

  it("does not render review-basis section when no patents have thinking text", () => {
    const report = makeMockReport({
      patent_analyses: [
        {
          patent_id: "US0000000001A1",
          title: "Test",
          assignee: "Test",
          expiry_date: null,
          claims_analyzed: [],
          risk_level: "low",
          risk_summary: "Low",
          design_around_suggestions: [],
          orange_book_info: null,
          model_used: "claude-3-opus",
          thinking_text: "",
          input_tokens: 100,
          output_tokens: 50,
        },
      ],
    });
    render(<AuditTab report={report} />);
    expect(screen.queryByText("Review Basis Notes")).not.toBeInTheDocument();
  });

  it("sorts triage entries by confidence descending", () => {
    const report = makeMockReport();
    const { container } = render(<AuditTab report={report} />);
    // Get triage table rows (skip header row)
    const _triageTable = screen
      .getByText("Pre-analysis Triage")
      .closest("[class]");
    // The first patent in the sorted triage should be US0000000001A1 (0.92 confidence)
    const _allPatentCells = container.querySelectorAll("td.font-mono");
    // Triage table patent cells start after the analysis selection table
    // We just verify the 92% appears before the 65%
    const text = container.textContent ?? "";
    const idx92 = text.indexOf("92%");
    const idx88 = text.indexOf("88%");
    const idx65 = text.indexOf("65%");
    expect(idx92).toBeLessThan(idx88);
    expect(idx88).toBeLessThan(idx65);
  });
});
