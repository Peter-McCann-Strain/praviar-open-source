import { describe, expect, it } from "vitest";
import { buildDashboardMetrics } from "@/components/dashboard/helpers";
import type { AnalysisListItem } from "@/types/api";

function analysisFixture(
  overrides: Partial<AnalysisListItem> = {},
): AnalysisListItem {
  return {
    id: "ana-base",
    compound_input: "aspirin",
    compound_name: "Aspirin",
    compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: "clear",
    blocking_patents_count: 0,
    total_patents_found: 10,
    executive_summary: "No blocking exposure identified.",
    estimated_cost_usd: 8,
    pipeline_duration_seconds: 180,
    flagged_for_review: false,
    created_at: "2026-04-17T12:00:00Z",
    updated_at: "2026-04-17T12:00:00Z",
    ...overrides,
  };
}

describe("buildDashboardMetrics", () => {
  it("keeps recent analyses newest-first while returning separate action-ranked docket", () => {
    const newestShared = analysisFixture({
      id: "ana-new",
      compound_name: "Newest Shared",
      share_active: true,
      share_view_count: 4,
      updated_at: "2026-04-20T12:00:00Z",
    });
    const olderChangesRequested = analysisFixture({
      id: "ana-change",
      compound_name: "Older Changes",
      review_status: {
        status: "changes_requested",
        is_persisted: true,
        updated_at: "2026-04-18T12:00:00Z",
      },
      updated_at: "2026-04-18T12:00:00Z",
    });
    const failed = analysisFixture({
      id: "ana-failed",
      compound_name: "Failed Run",
      status: "failed",
      overall_risk: null,
      updated_at: "2026-04-19T12:00:00Z",
    });
    const running = analysisFixture({
      id: "ana-running",
      compound_name: "Running Run",
      status: "running",
      current_step: 5,
      overall_risk: null,
      updated_at: "2026-04-21T12:00:00Z",
    });

    const metrics = buildDashboardMetrics([
      newestShared,
      olderChangesRequested,
      failed,
      running,
    ]);

    expect(metrics.recentAnalyses.map((analysis) => analysis.id)).toEqual([
      "ana-running",
      "ana-new",
      "ana-failed",
      "ana-change",
    ]);
    expect(
      metrics.priorityDocket.map((item) => [item.analysis.id, item.reason]),
    ).toEqual([
      ["ana-change", "Changes requested"],
      ["ana-failed", "Run failed"],
      ["ana-new", "Shared with 4 views"],
      ["ana-running", "Running step 5/8"],
    ]);
  });

  it("uses deterministic compound-name tie-breaks inside the same priority band", () => {
    const alpha = analysisFixture({
      id: "ana-alpha",
      compound_name: "Alpha",
      blocking_patents_count: 1,
      updated_at: "2026-04-18T12:00:00Z",
    });
    const beta = analysisFixture({
      id: "ana-beta",
      compound_name: "Beta",
      blocking_patents_count: 1,
      updated_at: "2026-04-18T12:00:00Z",
    });

    const metrics = buildDashboardMetrics([beta, alpha]);

    expect(metrics.priorityDocket.map((item) => item.analysis.id)).toEqual([
      "ana-alpha",
      "ana-beta",
    ]);
  });

  it("keeps dashboard activity previews bounded to five rows", () => {
    const analyses = Array.from({ length: 7 }, (_, index) =>
      analysisFixture({
        id: `ana-${index}`,
        compound_name: `Compound ${index}`,
        status: "running",
        overall_risk: null,
        current_step: index + 1,
        updated_at: `2026-04-${String(10 + index).padStart(2, "0")}T12:00:00Z`,
      }),
    );

    const metrics = buildDashboardMetrics(analyses);

    expect(metrics.recentAnalyses).toHaveLength(5);
    expect(metrics.priorityDocket).toHaveLength(5);
    expect(metrics.recentAnalyses.map((analysis) => analysis.id)).toEqual([
      "ana-6",
      "ana-5",
      "ana-4",
      "ana-3",
      "ana-2",
    ]);
  });

  it("counts persisted review decisions without inflating KPIs from transient review noise", () => {
    const persistedChanges = analysisFixture({
      id: "ana-persisted",
      review_status: {
        status: "changes_requested",
        is_persisted: true,
        updated_at: "2026-04-18T12:00:00Z",
      },
    });
    const transientChanges = analysisFixture({
      id: "ana-transient",
      review_status: {
        status: "changes_requested",
        is_persisted: false,
        updated_at: "2026-04-18T12:00:00Z",
      },
    });
    const flagged = analysisFixture({
      id: "ana-flagged",
      flagged_for_review: true,
    });

    const metrics = buildDashboardMetrics([
      persistedChanges,
      transientChanges,
      flagged,
    ]);

    expect(metrics.kpi.need_review).toBe(2);
    expect(metrics.priorityDocket.map((item) => item.analysis.id)).toContain(
      "ana-persisted",
    );
    expect(
      metrics.priorityDocket.map((item) => item.analysis.id),
    ).not.toContain("ana-transient");
  });

  it("marks a redacted dashboard window and excludes hidden risk from attention counts", () => {
    const restricted = analysisFixture({
      overall_risk: null,
      blocking_patents_count: null,
      risk_ratings_restricted: true,
    });

    const metrics = buildDashboardMetrics([restricted]);

    expect(metrics.riskRatingsRestricted).toBe(true);
    expect(metrics.kpi.high_risk_findings).toBe(0);
    expect(metrics.kpi.clear_compounds).toBe(0);
    expect(metrics.kpi.need_review).toBe(0);
  });
});
