import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { FTOReport } from "@praviar/shared-types";

import { ReasoningTab } from "@/components/report/reasoning-tab";

function makeMockReport(overrides: Partial<FTOReport> = {}): FTOReport {
  return {
    report_id: "rpt-reasoning",
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
      blocking_patents_count: 1,
      total_patents_analyzed: 1,
      key_risks: [],
      executive_summary: "Summary",
      summary_validation_issues: [],
    },
    patent_analyses: [],
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
    total_patents_found: 1,
    patents_after_triage: 1,
    search_sources_used: ["pubchem"],
    source_health: { entries: [] },
    scholarly_prior_art_count: 0,
    audit_trail: {
      search_funnel: [],
      triage_audit: [],
      analysis_audit: [],
      timing_data: [],
      total_patents_discovered: 1,
      patents_after_hard_filter: 1,
      patents_after_ranking: 1,
      patents_after_triage: 1,
      patents_analyzed: 1,
    },
    patent_narratives: {},
    disclaimer: "",
    llm_models_used: {},
    total_input_tokens: 0,
    total_output_tokens: 0,
    estimated_cost_usd: 0,
    step_token_usage: [],
    reasoning_traces: [],
    ...overrides,
  };
}

describe("ReasoningTab", () => {
  it("shows the empty state when no reasoning traces are available", () => {
    render(<ReasoningTab report={makeMockReport()} />);

    expect(
      screen.getByText(
        "Decision notes appear when adaptive review escalates to deeper evidence checks.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "First-stage matters stay on the fast path and keep this section brief.",
      ),
    ).toBeInTheDocument();
  });

  it("renders summary cards, groups traces by patent, and preserves collapsible trace details", () => {
    const report = makeMockReport({
      reasoning_traces: [
        {
          agent_type: "claim_analysis",
          model: "claude-3-opus",
          patent_id: "US12345678B2",
          rounds: [
            {
              round_number: 1,
              thinking_summary: "Initial pass",
              tool_calls: [
                {
                  tool_name: "patent_search",
                  duration_ms: 1200,
                  tool_output_summary: "Found one relevant result",
                },
              ],
              observations: "Observed overlap",
              scratchpad_delta: { notes: "added" },
              decision: "Proceed",
            },
          ],
          self_critique: "Need stronger support",
          revisions_made: ["Adjusted claim mapping"],
          final_output_summary: "Final conclusion",
          confidence: 0.87,
          total_input_tokens: 1200,
          total_output_tokens: 300,
          total_duration_ms: 2450,
        },
        {
          agent_type: "report",
          model: "claude-3.5-sonnet",
          patent_id: "",
          rounds: [],
          self_critique: "",
          revisions_made: [],
          final_output_summary: "",
          confidence: 0.42,
          total_input_tokens: 100,
          total_output_tokens: 25,
          total_duration_ms: 300,
        },
        {
          agent_type: "prior_art",
          model: "claude-3-opus",
          patent_id: "US12345678B2",
          rounds: [],
          self_critique: "",
          revisions_made: [],
          final_output_summary: "",
          confidence: 0.64,
          total_input_tokens: 500,
          total_output_tokens: 150,
          total_duration_ms: 600,
        },
      ],
    });

    render(<ReasoningTab report={report} />);

    expect(screen.getByText("Review Notes")).toBeInTheDocument();
    expect(
      screen.getByText("Review Notes").previousElementSibling,
    ).toHaveTextContent("3");
    expect(screen.getByText("Review Passes")).toBeInTheDocument();
    expect(
      screen.getByText("Review Passes").previousElementSibling,
    ).toHaveTextContent("1");
    expect(screen.getByText("Total Duration")).toBeInTheDocument();
    expect(
      screen.getByText("Total Effort").previousElementSibling,
    ).toHaveTextContent("2.3K");
    expect(
      screen.getByText("Total Duration").previousElementSibling,
    ).toHaveTextContent("3.4s");

    expect(screen.getAllByText("US12345678B2").length).toBeGreaterThan(1);
    expect(screen.getByText("General")).toBeInTheDocument();
    expect(screen.getByText("2 agents")).toBeInTheDocument();
    expect(screen.getByText("1 agent")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /expand claim analysis decision note for US12345678B2/i,
      }),
    );

    expect(screen.getByText("1 round")).toBeInTheDocument();
    expect(screen.getByText("2.5s")).toBeInTheDocument();
    expect(screen.getByText("1.2K in / 300 out")).toBeInTheDocument();
    expect(screen.getByText("Review Check")).toBeInTheDocument();
    expect(screen.getByText("Updates Made")).toBeInTheDocument();
    expect(screen.getByText("Decision Summary")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /round 1/i }));
    expect(screen.getByText("Review Basis")).toBeInTheDocument();
    expect(screen.getByText("Evidence Checks")).toBeInTheDocument();
    expect(screen.getByText("Findings")).toBeInTheDocument();
    expect(screen.getByText("Internal note withheld")).toBeInTheDocument();
    expect(screen.getByText("Initial pass")).toBeInTheDocument();
    expect(screen.getByText("patent_search")).toBeInTheDocument();
    expect(screen.getByText("Found one relevant result")).toBeInTheDocument();
    expect(screen.getByText("Observed overlap")).toBeInTheDocument();
    expect(
      screen.getByText(/Internal scratchpad changes are retained/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/"notes": "added"/)).not.toBeInTheDocument();
  });
});
