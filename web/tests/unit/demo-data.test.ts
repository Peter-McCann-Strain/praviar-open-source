import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import {
  DEMO_ANALYSIS_ID,
  createDemoAnalysis,
  getDemoAnalysis,
  getDemoReport,
  getDemoReportSummary,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
  normalizeDemoAnalysisId,
} from "@/lib/demo-data";

interface StructuredDemoReport extends FTOReport {
  clearance_decision?: {
    decision: "clear" | "unclear" | "blocked";
    decision_audit: {
      queried_sources_count: number;
      successful_sources_count: number;
    };
  };
  commercial_exposure?: {
    summary: string;
  };
}

describe("demo data structured decisioning", () => {
  it("normalizes legacy demo report aliases to the canonical analysis", () => {
    expect(normalizeDemoAnalysisId("demo-analysis-001")).toBe(DEMO_ANALYSIS_ID);
    expect(normalizeDemoAnalysisId("prv-demo-report")).toBe(DEMO_ANALYSIS_ID);
    expect(normalizeDemoAnalysisId("rpt_ana_fictional_0042")).toBe(
      DEMO_ANALYSIS_ID,
    );
    expect(normalizeDemoAnalysisId("PRV-2026-0142")).toBe(DEMO_ANALYSIS_ID);
    expect(getDemoAnalysis("demo-analysis-001")).toMatchObject({
      id: DEMO_ANALYSIS_ID,
      current_user_role: "admin",
      risk_ratings_restricted: false,
    });
    expect(isDemoAnalysisId("prv-demo-report")).toBe(true);
    expect(isSeedDemoAnalysisId("rpt_ana_fictional_0042")).toBe(true);
  });

  it("returns a review-required structured decision for the canonical showcase", () => {
    const report = getDemoReport(
      DEMO_ANALYSIS_ID,
    ) as StructuredDemoReport | null;

    expect(report?.clearance_decision?.decision).toBe("unclear");
    expect(
      report?.clearance_decision?.decision_audit.queried_sources_count,
    ).toBeGreaterThan(0);
    expect(report?.commercial_exposure?.summary).toMatch(
      /deeper legal review/i,
    );
    expect(report?.risk_summary.executive_summary).toMatch(/wholly fictional/i);
    expect(report?.claim_source_span_map?.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          patent_id: "XX-FICTION-0001-A1",
          support_status: "needs_review",
        }),
      ]),
    );
  });

  it("does not manufacture a report for the canonical failed-state projection", () => {
    const report = getDemoReport("ana_demo_003") as StructuredDemoReport | null;

    expect(report).toBeNull();
  });

  it("serves canonical reports and summaries for legacy demo aliases", () => {
    const report = getDemoReport("demo-analysis-001");
    const summary = getDemoReportSummary("prv-demo-report");

    expect(report?.report_id).toBe("rpt_ana_demo_001");
    expect(summary).toMatchObject({
      overall_risk: "medium",
      blocking_patents_count: 0,
    });
  });
});

describe("createDemoAnalysis", () => {
  it("uses the requested launch context instead of inheriting the seed analysis", () => {
    const analysis = createDemoAnalysis({
      compound_input: "celecoxib",
      trust_mode: "counsel",
      jurisdiction_bundle: "europe_uk",
      target_jurisdictions: ["EP", "UK"],
      development_stage: "clinical",
      asset_type_hint: "formulation",
      intended_actions: ["formulation_review"],
      product_context: {
        product_name: "Celecoxib capsule",
        dosage_form: "Capsule",
        route_of_administration: "Oral",
        owned_or_licensed_ip: "Internal option agreement",
      },
    });

    expect(analysis.launch_context).toMatchObject({
      trust_mode: "counsel",
      jurisdiction_bundle: "europe_uk",
      target_jurisdictions: ["EP", "UK"],
      development_stage: "clinical",
      asset_type_hint: "formulation",
      matter_type: "formulation",
      intended_actions: ["formulation_review"],
      product_context: {
        product_name: "Celecoxib capsule",
        dosage_form: "Capsule",
        route_of_administration: "Oral",
      },
    });
    expect(analysis.launch_context?.product_context).not.toHaveProperty(
      "manufacturing_route",
      "E. coli fermentation and crystallization",
    );
    expect(analysis.launch_context?.product_context).not.toHaveProperty(
      "owned_or_licensed_ip",
    );
  });
});
