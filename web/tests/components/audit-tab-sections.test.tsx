import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import { AuditReasoningCard } from "@/components/report/audit-tab-audit-reasoning-card";
import { AnalysisSelectionCard } from "@/components/report/audit-tab-analysis-selection-card";
import { DecisionEvidenceCard } from "@/components/report/audit-tab-decision-evidence-card";
import { HardFilterRejectionsCard } from "@/components/report/audit-tab-hard-filter-rejections-card";
import { TriageDecisionsCard } from "@/components/report/audit-tab-triage-decisions-card";

describe("audit tab section leaves", () => {
  it("renders hard filter rejections and hides empty cards", () => {
    const { container, rerender } = render(
      <HardFilterRejectionsCard
        rejectionEntries={[["Expired before filing", 2]]}
      />,
    );

    expect(screen.getByText("Hard Filter Rejections")).toBeInTheDocument();
    expect(screen.getByText("Expired before filing")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();

    rerender(<HardFilterRejectionsCard rejectionEntries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps long hard-filter reasons inside a labelled scroll region", () => {
    const longReason =
      "compound_structure_rejected_because_MARKUSH_SUBSTITUTION_CHAIN_AND_JURISDICTION_FILTER_TOKEN_HAS_NO_NATURAL_BREAKPOINT";

    render(<HardFilterRejectionsCard rejectionEntries={[[longReason, 127]]} />);

    const tableRegion = screen.getByRole("region", {
      name: "Hard filter rejections table",
    });
    expect(tableRegion).toHaveClass(
      "overflow-x-auto",
      "[scrollbar-gutter:stable]",
    );
    expect(tableRegion).toHaveAttribute("tabIndex", "0");
    expect(within(tableRegion).getByRole("table")).toHaveClass("min-w-[28rem]");
    expect(screen.getByText(longReason)).toHaveClass(
      "min-w-0",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("127")).toHaveClass("whitespace-nowrap");
  });

  it("renders triage and analysis tables with selection markers", () => {
    const { container } = render(
      <>
        <TriageDecisionsCard
          triageEntries={[
            {
              patent_id: "US123",
              relevance: "relevant",
              confidence: 0.87,
              reason: "Direct overlap",
              passed_triage: true,
            },
          ]}
        />
        <AnalysisSelectionCard
          analysisEntries={[
            {
              patent_id: "US123",
              selected_for_analysis: true,
              selection_reason: "High relevance score",
              risk_level: "high",
              selected_for_doe: false,
              selected_for_invalidity: true,
            },
          ]}
        />
      </>,
    );

    expect(screen.getByText("Pre-analysis Triage")).toBeInTheDocument();
    expect(screen.getAllByText("Retrieval relevance").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Triage confidence").length).toBeGreaterThan(0);
    expect(screen.getByText("87%")).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toBeTruthy();
    expect(screen.getByText("Candidate Analysis Routing")).toBeInTheDocument();
    expect(screen.getAllByText("Validity review").length).toBeGreaterThan(0);
    const mobileValidityLabels = screen
      .getAllByText("Validity review")
      .filter((node) => node.tagName === "SPAN");
    expect(mobileValidityLabels).toHaveLength(1);
    expect(mobileValidityLabels[0]).not.toHaveAttribute("aria-hidden");
    expect(
      screen.getByText(/workflow routing, not completed findings/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("\u2713")).toHaveLength(2);
    expect(screen.getByText("\u2715")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Selected")).toHaveLength(2);
    expect(screen.getByLabelText("Not selected")).toBeInTheDocument();
  });

  it("uses the neutral report relevance marker for not-relevant decisions", () => {
    const { container } = render(
      <TriageDecisionsCard
        triageEntries={[
          {
            patent_id: "US999",
            relevance: "not_relevant",
            confidence: 0.51,
            reason: "Outside the claim scope",
            passed_triage: false,
          },
        ]}
      />,
    );

    expect(screen.getByText("not relevant")).toBeInTheDocument();
    expect(container.querySelector(".praviar-chart-swatch")).toHaveAttribute(
      "style",
      expect.stringContaining("var(--text-tertiary)"),
    );
  });

  it("expands the review-basis panel to show note text", () => {
    render(
      <AuditReasoningCard
        thinkingPatents={[
          {
            patent_id: "US456",
            thinking_text: "This patent covers the process directly.",
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /US456 - Review basis note/ }),
    );
    expect(
      screen.getByText("This patent covers the process directly."),
    ).toBeInTheDocument();
  });

  it("redacts diagnostics from review-basis notes", () => {
    render(
      <AuditReasoningCard
        thinkingPatents={[
          {
            patent_id: "US456",
            thinking_text:
              "Observed postgres://secret-host/praviar sk_live_secret SELECT * FROM claims Traceback provider stack",
          },
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /US456 - Review basis note/ }),
    );
    expect(
      screen.queryByText(/postgres:\/\/secret-host/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/SELECT \*/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/\[redacted connection string\]/i),
    ).toBeInTheDocument();
  });

  it("renders structured decision evidence when present", () => {
    const report = {
      clearance_decision: {
        decision: "blocked",
        decision_confidence: 0.89,
        evidence_quality: 0.76,
        decision_reasoning: [
          "A blocking US process patent remains unresolved.",
        ],
        decision_audit: {
          queried_sources_count: 6,
          successful_sources_count: 5,
          material_patents_reviewed: 9,
          material_us_patents: 6,
          material_ep_patents: 3,
          patents_with_claims: 8,
          patents_with_family: 9,
          us_patents_with_prosecution_context: 5,
          ep_patents_with_register_context: 2,
          analysis_failures_count: 1,
          failed_sources: ["epo_search"],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: ["One EP family remains underdeveloped."],
          evidence_warnings: ["US0000000001A1 remains blocking after review."],
          search_iterations: 4,
          coverage_summary: {
            queried_source_names: [
              "pubchem_sdq",
              "surechembl",
              "bigquery",
              "patcid",
              "epo_search",
              "lens",
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
              "US0000000001A1",
              "US0000000002A1",
              "US0000000003A1",
            ],
            reviewed_us_patent_ids: ["US0000000001A1", "US0000000002A1"],
            reviewed_ep_patent_ids: ["EP3456789B1"],
            patents_missing_claims: ["EP3456789B1"],
            patents_missing_family_context: ["US0000000003A1"],
            us_patents_missing_prosecution_context: ["US0000000002A1"],
            ep_patents_missing_register_context: ["EP3456789B1"],
            failed_analysis_patent_ids: ["EP3456789B1"],
            verification_gaps: [
              "One claim chart citation could not be verified.",
            ],
          },
          decisive_references: [
            {
              category: "blocking_patent",
              patent_id: "US0000000001A1",
              jurisdiction: "US",
              summary:
                "Independent claim 1 still reads on the assessed fermentation route.",
            },
          ],
        },
      },
    } as unknown as FTOReport;

    render(<DecisionEvidenceCard report={report} />);

    expect(screen.getByText("Decision Evidence")).toBeInTheDocument();
    expect(screen.getByText("Coverage Gaps")).toBeInTheDocument();
    expect(screen.getByText("Blocking Patent")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Independent claim 1 still reads on the assessed fermentation route.",
      ),
    ).toBeInTheDocument();
  });
});
