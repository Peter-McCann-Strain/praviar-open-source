import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import {
  getClearanceDecision,
  getCommercialExposure,
  getDecisionSentence,
} from "@/components/report/report-decision-helpers";

describe("report-decision-helpers", () => {
  it("returns null when the structured clearance decision is incomplete", () => {
    const report = {
      clearance_decision: {
        decision: "clear",
      },
    } as unknown as FTOReport;

    expect(getClearanceDecision(report)).toBeNull();
    expect(getDecisionSentence(report)).toBeNull();
  });

  it("returns the structured clearance decision when required fields are present", () => {
    const report = {
      clearance_decision: {
        decision: "clear",
        decision_confidence: 0.82,
        evidence_quality: 0.91,
        decision_reasoning: [
          "All reviewed patents resolved below blocking threshold.",
        ],
        decision_audit: {
          queried_sources_count: 6,
          successful_sources_count: 6,
          material_patents_reviewed: 8,
          material_us_patents: 5,
          material_ep_patents: 3,
          patents_with_claims: 8,
          patents_with_family: 8,
          us_patents_with_prosecution_context: 5,
          ep_patents_with_register_context: 3,
          analysis_failures_count: 0,
          failed_sources: [],
          evidence_sufficient_for_clearance: true,
          insufficiency_reasons: [],
          evidence_warnings: [],
          search_iterations: 5,
          coverage_summary: {
            queried_source_names: ["pubchem_sdq", "surechembl"],
            successful_source_names: ["pubchem_sdq", "surechembl"],
            failed_source_names: [],
            reviewed_patent_ids: ["US1", "EP1"],
            reviewed_us_patent_ids: ["US1"],
            reviewed_ep_patent_ids: ["EP1"],
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

    expect(getClearanceDecision(report)?.decision).toBe("clear");
    expect(getDecisionSentence(report)).toContain(
      "Screening status: no blockers identified",
    );
  });

  it("returns null when the commercial exposure payload is incomplete", () => {
    const report = {
      commercial_exposure: {
        summary: "Incomplete payload",
      },
    } as unknown as FTOReport;

    expect(getCommercialExposure(report)).toBeNull();
  });

  it("returns the commercial exposure payload when required fields are present", () => {
    const report = {
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
    } as unknown as FTOReport;

    expect(getCommercialExposure(report)?.blocking_patent_ids).toEqual([
      "US0000000001A1",
    ]);
  });
});
