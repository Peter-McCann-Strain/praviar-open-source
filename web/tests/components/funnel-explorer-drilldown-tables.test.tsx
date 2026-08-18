import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import {
  AnalysisTable,
  HardFilterTable,
  RankingCutTable,
  TriageTable,
} from "@/components/report/funnel-explorer-drilldown-tables";
import type {
  AnalysisAuditEntry,
  SearchFunnelEntry,
  TriageAuditEntry,
} from "@/components/report/funnel-explorer-helpers";

function makeSearchEntry(
  overrides: Partial<SearchFunnelEntry> = {},
): SearchFunnelEntry {
  return {
    patent_id: "US-1",
    title: "Example patent",
    source: "google_patents",
    match_score: 0.9,
    match_type: "similarity",
    query_used: "example",
    passed_hard_filter: false,
    filter_reason: "expired_patent",
    ranked_position: 1,
    confidence_score: 0.88,
    family_broadest: false,
    ...overrides,
  };
}

function makeTriageEntry(
  overrides: Partial<TriageAuditEntry> = {},
): TriageAuditEntry {
  return {
    patent_id: "US-100",
    relevance: "relevant",
    confidence: 0.92,
    reason: "Strong overlap with the query compound.",
    ...overrides,
  };
}

function makeAnalysisEntry(
  overrides: Partial<AnalysisAuditEntry> = {},
): AnalysisAuditEntry {
  return {
    patent_id: "US-200",
    selected_for_analysis: true,
    selection_reason: "Top-ranked blocking patent.",
    risk_level: "high",
    selected_for_doe: true,
    selected_for_invalidity: false,
    ...overrides,
  };
}

describe("funnel explorer drilldown tables", () => {
  it("groups hard-filter rejections by reason", () => {
    render(
      <HardFilterTable
        entries={[
          makeSearchEntry(),
          makeSearchEntry({ patent_id: "US-2" }),
          makeSearchEntry({ patent_id: "US-3", filter_reason: "foreign_only" }),
        ]}
      />,
    );

    expect(
      screen.getByText("3 patents removed by hard filters"),
    ).toBeInTheDocument();
    expect(screen.getByText("expired patent")).toBeInTheDocument();
    expect(screen.getByText("foreign only")).toBeInTheDocument();
  });

  it("shows row-level composite-pool and final-rank cut receipts", () => {
    render(
      <RankingCutTable
        entries={[
          makeSearchEntry({
            patent_id: "US-RANK-CUT",
            passed_hard_filter: true,
            included_in_triage: false,
            filter_reason: "rank_cut_max_results",
            exclusion_stage: "final_rank",
            candidate_index: 12,
            composite_rank: 4,
            pre_cut_rank: 7,
            final_blend_score: 0.618,
          }),
          makeSearchEntry({
            patent_id: "US-POOL-CUT",
            passed_hard_filter: true,
            included_in_triage: false,
            filter_reason: "composite_pool_cut",
            exclusion_stage: "composite_pool",
            candidate_index: 13,
            composite_rank: 1001,
          }),
        ]}
      />,
    );

    expect(
      screen.getByText(/2 candidates passed hard filters/i),
    ).toBeInTheDocument();
    expect(screen.getByText("US-RANK-CUT")).toBeInTheDocument();
    expect(screen.getByText("US-POOL-CUT")).toBeInTheDocument();
    expect(screen.getByText("rank cut max results")).toBeInTheDocument();
    expect(screen.getByText("0.618")).toBeInTheDocument();
  });

  it("wraps long hard-filter reasons and patent identifiers", () => {
    const longReason =
      "uninterpretableMarkushSubstitutionPatternWithoutSpacesForResponsiveStress";
    const longPatentId =
      "WO202699999999A1-EXTREMELY-LONG-FAMILY-MEMBER-WITHOUT-SPACES";

    render(
      <HardFilterTable
        entries={[
          makeSearchEntry({
            filter_reason: longReason,
            patent_id: longPatentId,
          }),
        ]}
      />,
    );

    expect(screen.getByText(longReason)).toHaveClass(
      "min-w-0",
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longPatentId)).toHaveClass(
      "max-w-full",
      "break-all",
      "[overflow-wrap:anywhere]",
    );
  });

  it("filters and paginates triage entries", () => {
    const { container } = render(
      <TriageTable
        entries={[
          ...Array.from({ length: 22 }, (_, index) =>
            makeTriageEntry({
              patent_id: `US-${index}`,
              relevance: index < 21 ? "relevant" : "not_relevant",
              confidence: 1 - index * 0.01,
            }),
          ),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /relevant \(21\)/i }));
    expect(screen.getByText(/showing 1–20 of 21/i)).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toHaveAttribute(
      "style",
      expect.stringContaining("var(--color-success)"),
    );

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/showing 21–21 of 21/i)).toBeInTheDocument();
  });

  it("renders non-relevant triage as a neutral swatch, not an error marker", () => {
    const { container } = render(
      <TriageTable
        entries={[
          makeTriageEntry({
            patent_id: "US-neutral",
            relevance: "not_relevant",
          }),
        ]}
      />,
    );

    expect(screen.getByText("not relevant")).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toHaveAttribute(
      "style",
      expect.stringContaining("var(--text-tertiary)"),
    );
  });

  it("wraps long triage reasons on compact layouts", () => {
    const longReason =
      "sameScaffoldSameSaltFormSameIndicationSameRouteNoSpacesResponsiveStressToken";

    render(
      <TriageTable
        entries={[
          makeTriageEntry({
            reason: longReason,
          }),
        ]}
      />,
    );

    expect(screen.getByText(longReason)).toHaveClass(
      "min-w-0",
      "break-words",
      "[overflow-wrap:anywhere]",
      "md:truncate",
    );
  });

  it("renders analysis selections and risk badges", () => {
    render(
      <AnalysisTable
        entries={[
          makeAnalysisEntry(),
          makeAnalysisEntry({
            patent_id: "US-201",
            selected_for_analysis: false,
            risk_level: null,
            selected_for_doe: false,
            selected_for_invalidity: true,
          }),
        ]}
      />,
    );

    expect(screen.getByText("US-200")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("US-201")).toBeInTheDocument();
    const mobileSelectedLabels = screen
      .getAllByText("Selected")
      .filter((node) => node.tagName === "SPAN");
    expect(mobileSelectedLabels).toHaveLength(2);
    for (const label of mobileSelectedLabels) {
      expect(label).not.toHaveAttribute("aria-hidden");
    }
  });
});
