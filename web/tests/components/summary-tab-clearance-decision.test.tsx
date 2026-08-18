import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import { ClearanceDecisionSection } from "@/components/report/summary-tab-clearance-decision";

describe("ClearanceDecisionSection", () => {
  it("renders nothing when the structured decision is absent", () => {
    const { container } = render(
      <ClearanceDecisionSection report={{} as FTOReport} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("labels heuristic evidence as a bounded score, not a probability", () => {
    const report = {
      clearance_decision: {
        decision: "clear",
        decision_confidence: 88,
        evidence_quality: 74,
        decision_reasoning: [],
        decision_audit: {
          queried_sources_count: 6,
          successful_sources_count: 5,
          material_patents_reviewed: 11,
          material_us_patents: 7,
          material_ep_patents: 4,
          patents_with_claims: 10,
          patents_with_family: 11,
          us_patents_with_prosecution_context: 6,
          ep_patents_with_register_context: 3,
          analysis_failures_count: 1,
          failed_sources: ["epo_search"],
          evidence_sufficient_for_clearance: true,
          insufficiency_reasons: [],
          evidence_warnings: [],
          search_iterations: 5,
          coverage_summary: {
            queried_source_names: [],
            successful_source_names: [],
            failed_source_names: [],
            reviewed_patent_ids: [],
            reviewed_us_patent_ids: [],
            reviewed_ep_patent_ids: [],
            patents_missing_claims: [],
            patents_missing_family_context: [],
            us_patents_missing_prosecution_context: [],
            ep_patents_missing_register_context: [],
            failed_analysis_patent_ids: [],
            verification_gaps: [],
          },
          decisive_references: [],
        },
      },
    } as unknown as FTOReport;

    render(<ClearanceDecisionSection report={report} />);

    expect(screen.queryByText("88%")).not.toBeInTheDocument();
    expect(screen.getByText("74 / 100")).toBeInTheDocument();
    expect(screen.getByText("Evidence completeness")).toBeInTheDocument();
  });

  it("renders structured decision, jurisdiction outcomes, and future risk", () => {
    const report = {
      clearance_decision: {
        decision: "blocked",
        decision_confidence: 0.88,
        evidence_quality: 0.74,
        decision_reasoning: [
          "US fermentation claims remain unresolved.",
          "EP coverage remains mixed because one family is still pending full register review.",
        ],
        decision_audit: {
          queried_sources_count: 6,
          successful_sources_count: 5,
          material_patents_reviewed: 11,
          material_us_patents: 7,
          material_ep_patents: 4,
          patents_with_claims: 10,
          patents_with_family: 11,
          us_patents_with_prosecution_context: 6,
          ep_patents_with_register_context: 3,
          analysis_failures_count: 1,
          failed_sources: ["epo_search"],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: [
            "EP register collection is incomplete for one material family.",
          ],
          evidence_warnings: ["Blocking exposure remains in US."],
          search_iterations: 5,
          coverage_summary: {
            queried_source_names: [
              "pubchem_sdq",
              "surechembl",
              "bigquery",
              "patcid",
              "lens",
              "epo_search",
            ],
            successful_source_names: [
              "pubchem_sdq",
              "surechembl",
              "bigquery",
              "patcid",
              "lens",
            ],
            failed_source_names: ["epo_search"],
            reviewed_patent_ids: [
              "US1",
              "US2",
              "US3",
              "US4",
              "US5",
              "US6",
              "US7",
              "EP1",
              "EP2",
              "EP3",
              "EP4",
            ],
            reviewed_us_patent_ids: [
              "US1",
              "US2",
              "US3",
              "US4",
              "US5",
              "US6",
              "US7",
            ],
            reviewed_ep_patent_ids: ["EP1", "EP2", "EP3", "EP4"],
            patents_missing_claims: ["EP4"],
            patents_missing_family_context: [],
            us_patents_missing_prosecution_context: ["US7"],
            ep_patents_missing_register_context: ["EP4"],
            failed_analysis_patent_ids: ["EP4"],
            verification_gaps: [],
          },
          decisive_references: [],
        },
      },
      jurisdiction_decisions: [
        {
          jurisdiction: "US",
          decision: "blocked",
          decision_confidence: 0.91,
          evidence_quality: 0.81,
          reviewed_patent_ids: [
            "US1",
            "US2",
            "US3",
            "US4",
            "US5",
            "US6",
            "US7",
          ],
          blocking_patent_ids: ["US0000000001A1"],
          reasoning: ["US process claims remain blocking."],
        },
        {
          jurisdiction: "EP",
          decision: "unclear",
          decision_confidence: 0.63,
          evidence_quality: 0.58,
          reviewed_patent_ids: ["EP1", "EP2", "EP3", "EP4"],
          blocking_patent_ids: [],
          reasoning: ["EP register evidence is incomplete."],
        },
      ],
      commercial_exposure: {
        damages_injunction_risk: "high",
        business_severity: "high",
        blocking_patent_ids: ["US0000000001A1"],
        rationale: [
          "Launch-at-risk posture would expose the product to immediate injunction pressure.",
        ],
        summary:
          "Commercial launch would face substantial injunction and damages exposure in the US.",
      },
      future_risk: [
        {
          patent_id: "EP3456789A1",
          jurisdiction: "EP",
          risk_type: "pending_continuation",
          severity: "medium",
          summary:
            "A related EP continuation remains pending with overlapping formulation language.",
        },
      ],
    } as unknown as FTOReport;

    render(<ClearanceDecisionSection report={report} />);

    expect(screen.getByText("Preliminary Review Posture")).toBeInTheDocument();
    expect(screen.queryByText("Clearance Decision")).not.toBeInTheDocument();
    expect(screen.getByText(/for counsel review/i)).toBeInTheDocument();
    expect(screen.getAllByText("Potential blocker")).toHaveLength(2);
    expect(screen.getByText("Commercial Exposure")).toBeInTheDocument();
    expect(screen.getByText("Jurisdiction Postures")).toBeInTheDocument();
    expect(screen.getByText("Future Risk Signals")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Commercial launch would face substantial injunction and damages exposure in the US.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/EP · pending continuation/i)).toBeInTheDocument();
  });
});
