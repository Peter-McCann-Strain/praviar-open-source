import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import { buildConfidenceDashboardState } from "@/components/report/confidence-dashboard-helpers";

describe("confidence-dashboard-helpers", () => {
  it("derives a high-confidence state from healthy sources", () => {
    const report = {
      generated_at: "2026-03-12T10:00:00Z",
      search_sources_used: ["pubchem", "bigquery", "surechembl"],
      source_health: {
        entries: [
          {
            source: "pubchem",
            status: "ok",
            patent_count: 150,
            error_message: "",
          },
          {
            source: "bigquery",
            status: "ok",
            patent_count: 200,
            error_message: "",
          },
          {
            source: "surechembl",
            status: "ok",
            patent_count: 39,
            error_message: "",
          },
        ],
      },
      data_limitations: [],
      analysis_failures: [],
    } as unknown as FTOReport;

    const state = buildConfidenceDashboardState(report);

    expect(state.band).toBe("HIGH");
    expect(state.summaryLabel).toBe("3/3 source providers healthy");
    expect(state.coverageLabel).toBe("100%");
  });

  it("drops to low confidence when evidence quality and source coverage are weak", () => {
    const report = {
      generated_at: "2026-03-12T10:00:00Z",
      search_sources_used: ["pubchem", "epo_ops", "lens"],
      source_health: {
        entries: [
          {
            source: "pubchem",
            status: "ok",
            patent_count: 10,
            error_message: "",
          },
          {
            source: "epo_ops",
            status: "failed",
            patent_count: 0,
            error_message: "down",
          },
          {
            source: "lens",
            status: "skipped",
            patent_count: 0,
            error_message: "timed out",
          },
        ],
      },
      data_limitations: [],
      analysis_failures: [],
      clearance_decision: {
        decision: "unclear",
        decision_confidence: 0.7,
        evidence_quality: 0.55,
        decision_reasoning: ["Record incomplete."],
        decision_audit: {
          queried_sources_count: 3,
          successful_sources_count: 1,
          material_patents_reviewed: 4,
          material_us_patents: 3,
          material_ep_patents: 1,
          patents_with_claims: 4,
          patents_with_family: 4,
          us_patents_with_prosecution_context: 2,
          ep_patents_with_register_context: 0,
          analysis_failures_count: 0,
          failed_sources: ["epo_ops", "lens"],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: ["EP evidence incomplete."],
          evidence_warnings: ["Verification incomplete."],
          search_iterations: 3,
          coverage_summary: {
            queried_source_names: ["pubchem", "epo_ops", "lens"],
            successful_source_names: ["pubchem"],
            failed_source_names: ["epo_ops", "lens"],
            reviewed_patent_ids: ["US1", "US2", "US3", "EP1"],
            reviewed_us_patent_ids: ["US1", "US2", "US3"],
            reviewed_ep_patent_ids: ["EP1"],
            patents_missing_claims: ["EP1"],
            patents_missing_family_context: [],
            us_patents_missing_prosecution_context: [],
            ep_patents_missing_register_context: ["EP1"],
            failed_analysis_patent_ids: [],
            verification_gaps: [
              "One citation could not be re-validated automatically.",
            ],
          },
          decisive_references: [],
        },
      },
    } as unknown as FTOReport;

    const state = buildConfidenceDashboardState(report);

    expect(state.band).toBe("LOW");
    expect(state.summaryLabel).toContain(
      "4 patents · 1/3 source providers healthy · 1 failed",
    );
    expect(state.failedSources).toHaveLength(2);
  });

  it("treats not configured sources as known source gaps", () => {
    const report = {
      generated_at: "2026-03-12T10:00:00Z",
      search_sources_used: ["pubchem", "bigquery", "patcid"],
      source_health: {
        entries: [
          {
            source: "pubchem",
            status: "ok",
            patent_count: 10,
            error_message: "",
          },
          {
            source: "bigquery",
            status: "ok",
            patent_count: 12,
            error_message: "",
          },
          {
            source: "patcid",
            status: "not_configured",
            patent_count: 0,
            error_message: "",
          },
        ],
      },
      data_limitations: [],
      analysis_failures: [],
    } as unknown as FTOReport;

    const state = buildConfidenceDashboardState(report);

    expect(state.band).toBe("MODERATE");
    expect(state.summaryLabel).toBe(
      "2/3 source providers healthy · 1 need review",
    );
    expect(state.coverageLabel).toBe("67%");
    expect(state.failedSources).toEqual([
      expect.objectContaining({
        source: "patcid",
        status: "not_configured",
      }),
    ]);
  });

  it("fails closed when providers are listed without a source-health ledger", () => {
    const report = {
      generated_at: "2026-03-12T10:00:00Z",
      search_sources_used: ["pubchem", "bigquery", "surechembl"],
      data_limitations: [],
      analysis_failures: [],
    } as unknown as FTOReport;

    const state = buildConfidenceDashboardState(report);

    expect(state.band).toBe("LOW");
    expect(state.coverageLabel).toBe("0%");
    expect(state.summaryLabel).toBe(
      "3 source providers listed · health unreported",
    );
    expect(state.failedSources).toHaveLength(3);
  });

  it("uses provider health instead of a narrower successful decision-audit ratio", () => {
    const report = {
      generated_at: "2026-03-12T10:00:00Z",
      search_sources_used: ["pubchem", "bigquery", "surechembl", "epo_ops"],
      source_health: {
        entries: [
          { source: "pubchem", status: "ok" },
          { source: "bigquery", status: "ok" },
          { source: "surechembl", status: "ok" },
          { source: "epo_ops", status: "failed" },
        ],
      },
      data_limitations: [],
      analysis_failures: [],
      clearance_decision: {
        decision: "unclear",
        decision_confidence: 0.8,
        evidence_quality: 0.9,
        decision_reasoning: [],
        decision_audit: {
          queried_sources_count: 3,
          successful_sources_count: 3,
          material_patents_reviewed: 4,
          material_us_patents: 4,
          material_ep_patents: 0,
          patents_with_claims: 4,
          patents_with_family: 4,
          us_patents_with_prosecution_context: 4,
          ep_patents_with_register_context: 0,
          analysis_failures_count: 0,
          failed_sources: ["epo_ops"],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: ["One provider failed."],
          evidence_warnings: [],
          search_iterations: 1,
          coverage_summary: {
            queried_source_names: ["pubchem", "bigquery", "surechembl"],
            successful_source_names: ["pubchem", "bigquery", "surechembl"],
            failed_source_names: ["epo_ops"],
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

    const state = buildConfidenceDashboardState(report);

    expect(state.coverageLabel).toBe("75%");
    expect(state.band).toBe("MODERATE");
    expect(state.summaryLabel).toBe(
      "4 patents · 3/4 source providers healthy · 1 failed",
    );
    expect(state.summaryLabel).not.toContain("3/3");
  });
});
