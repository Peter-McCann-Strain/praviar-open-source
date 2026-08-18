import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import { VerdictBanner } from "@/components/report/verdict-banner";
import type { FTOReport } from "@praviar/shared-types";

function withRisk(risk: string): FTOReport {
  return {
    ...TEST_REPORT,
    risk_summary: { ...TEST_REPORT.risk_summary, overall_risk: risk },
  } as FTOReport;
}

function withStructuredDecision({
  decisionConfidence = 0.82,
  evidenceQuality = 0.91,
}: {
  decisionConfidence?: number;
  evidenceQuality?: number;
} = {}): FTOReport {
  return {
    ...TEST_REPORT,
    clearance_decision: {
      decision: "clear",
      decision_confidence: decisionConfidence,
      evidence_quality: evidenceQuality,
      decision_reasoning: [
        "All reviewed US and EP patents resolved below blocking threshold.",
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
          queried_source_names: [
            "pubchem_sdq",
            "surechembl",
            "bigquery",
            "bigquery_annotations",
            "patcid",
            "epo_search",
          ],
          successful_source_names: [
            "pubchem_sdq",
            "surechembl",
            "bigquery",
            "bigquery_annotations",
            "patcid",
            "epo_search",
          ],
          failed_source_names: [],
          reviewed_patent_ids: [
            "US1",
            "US2",
            "US3",
            "US4",
            "US5",
            "EP1",
            "EP2",
            "EP3",
          ],
          reviewed_us_patent_ids: ["US1", "US2", "US3", "US4", "US5"],
          reviewed_ep_patent_ids: ["EP1", "EP2", "EP3"],
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
}

describe("VerdictBanner", () => {
  it("renders role=alert for HIGH risk", () => {
    const { container } = render(<VerdictBanner report={TEST_REPORT} />);
    expect(container.querySelector("[role='alert']")).toBeInTheDocument();
  });

  it("renders role=status for LOW risk", () => {
    const report = withRisk("low");
    const { container } = render(<VerdictBanner report={report} />);
    expect(container.querySelector("[role='status']")).toBeInTheDocument();
  });

  it("shows blocking count for HIGH risk", () => {
    render(<VerdictBanner report={TEST_REPORT} />);
    expect(screen.getByText(/3 blocking patent/i)).toBeInTheDocument();
  });

  it("shows verdict sentence for HIGH risk", () => {
    render(<VerdictBanner report={TEST_REPORT} />);
    expect(screen.getByText(/Expert review required/)).toBeInTheDocument();
  });

  it("shows verdict sentence for MEDIUM risk", () => {
    const report = withRisk("medium");
    render(<VerdictBanner report={report} />);
    expect(screen.getByText(/require attention/)).toBeInTheDocument();
  });

  it("shows verdict sentence for LOW risk", () => {
    const report = withRisk("low");
    render(<VerdictBanner report={report} />);
    expect(screen.getByText(/Lower-risk screening result/)).toBeInTheDocument();
  });

  it("shows verdict sentence for CLEAR risk", () => {
    const report = {
      ...withRisk("clear"),
      jurisdiction_decisions: [],
      search_sources_used: ["pubchem", "surechembl", "bigquery"],
    } as FTOReport;
    render(<VerdictBanner report={report} />);
    expect(
      screen.getByText(/No blockers identified in the reviewed record/),
    ).toBeInTheDocument();
    expect(screen.getByText(/3 sources/)).toBeInTheDocument();
    expect(screen.queryByText(/3 jurisdictions/)).not.toBeInTheDocument();
  });

  it("uses jurisdiction language only when jurisdiction decisions exist", () => {
    const report = {
      ...withRisk("clear"),
      jurisdiction_decisions: [{ jurisdiction: "US" }, { jurisdiction: "EP" }],
      search_sources_used: ["pubchem", "surechembl", "bigquery"],
    } as FTOReport;
    render(<VerdictBanner report={report} />);

    expect(screen.getByText(/2 jurisdictions/)).toBeInTheDocument();
    expect(screen.queryByText(/3 sources/)).not.toBeInTheDocument();
  });

  it("renders metric pills", () => {
    render(<VerdictBanner report={TEST_REPORT} />);
    expect(screen.getByText(/Reviewed/)).toBeInTheDocument();
    expect(screen.getByText(/Blocking/)).toBeInTheDocument();
    expect(screen.getByText(/Sources/)).toBeInTheDocument();
  });

  it("defaults to passive pending review without action controls", () => {
    render(<VerdictBanner report={TEST_REPORT} />);

    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve report" }),
    ).not.toBeInTheDocument();
  });

  it("renders recorded approval metadata from the review workflow", () => {
    render(
      <VerdictBanner
        report={TEST_REPORT}
        approvalStatus="approved"
        approvalApprover="Demo Counsel"
        approvalApprovedAt="2026-04-24T10:00:00.000Z"
      />,
    );

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/by Demo Counsel on Apr 24/i)).toBeInTheDocument();
    expect(screen.queryByText("Pending Review")).not.toBeInTheDocument();
  });

  it("renders changes requested without falling back to pending copy", () => {
    render(
      <VerdictBanner
        report={TEST_REPORT}
        approvalStatus="changes_requested"
        approvalApprover="Review lead"
      />,
    );

    expect(screen.getByText("Changes Requested")).toBeInTheDocument();
    expect(screen.getByText(/by Review lead/i)).toBeInTheDocument();
    expect(screen.queryByText("Pending Review")).not.toBeInTheDocument();
  });

  it("has aria-live polite", () => {
    const { container } = render(<VerdictBanner report={TEST_REPORT} />);
    expect(container.querySelector("[aria-live='polite']")).toBeInTheDocument();
  });

  it("prefers the structured clearance decision when present", () => {
    const report = withStructuredDecision();

    render(<VerdictBanner report={report} />);

    expect(
      screen.getByText("No blockers in reviewed evidence"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Screening status: no blockers identified in 8 material patents reviewed/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/91 \/ 100 Evidence-completeness score/),
    ).toBeInTheDocument();
  });

  it("does not multiply percent-shaped structured decision metrics", () => {
    render(
      <VerdictBanner
        report={withStructuredDecision({
          decisionConfidence: 82,
          evidenceQuality: 91,
        })}
      />,
    );

    expect(
      screen.getByText(/91 \/ 100 Evidence-completeness score/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/9100 \/ 100 Evidence-completeness score/),
    ).not.toBeInTheDocument();
  });
});
