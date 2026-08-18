import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { FTOReport } from "@praviar/shared-types";

import { createMotionMock } from "../helpers/mock-motion";

vi.mock("motion/react", () => createMotionMock());

import { ConfidenceDashboard } from "@/components/report/confidence-dashboard";

const mockReport = {
  generated_at: "2026-03-12T10:00:00Z",
  search_sources_used: ["pubchem", "bigquery", "surechembl"],
  source_health: {
    entries: [
      { source: "pubchem", status: "ok", patent_count: 150, error_message: "" },
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

describe("ConfidenceDashboard", () => {
  it("renders confidence band badge", () => {
    render(<ConfidenceDashboard report={mockReport} />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("shows source count", () => {
    render(<ConfidenceDashboard report={mockReport} />);
    expect(
      screen.getByText(/3\/3 source providers healthy/),
    ).toBeInTheDocument();
  });

  it("starts collapsed", () => {
    render(<ConfidenceDashboard report={mockReport} />);
    expect(screen.getByRole("button")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("can start expanded when used in the summary workbench rail", () => {
    const { container } = render(
      <ConfidenceDashboard report={mockReport} defaultExpanded />,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Patent Databases")).toBeInTheDocument();
    const sourceMatrix =
      screen.getByText("Patent Databases").nextElementSibling;
    expect(sourceMatrix).toHaveClass("grid-cols-2");
    expect(sourceMatrix).not.toHaveClass("sm:grid-cols-3");
    expect(container).toHaveTextContent("patents");
  });

  it("expands on click to show source matrix", () => {
    render(<ConfidenceDashboard report={mockReport} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Patent Databases")).toBeInTheDocument();
    expect(screen.getByText("pubchem")).toBeInTheDocument();
  });

  it("shows HIGH band when all sources covered and no failures", () => {
    const fullReport = {
      ...mockReport,
      search_sources_used: [
        "pubchem",
        "bigquery",
        "surechembl",
        "patcid",
        "epo_ops",
        "lens",
      ],
    } as unknown as FTOReport;
    render(<ConfidenceDashboard report={fullReport} />);
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("uses provider health globally while retaining decision warnings", () => {
    const structuredReport = {
      ...mockReport,
      clearance_decision: {
        decision: "unclear",
        decision_confidence: 0.71,
        evidence_quality: 0.58,
        decision_reasoning: ["The record remains incomplete in EP."],
        decision_audit: {
          queried_sources_count: 5,
          successful_sources_count: 3,
          material_patents_reviewed: 7,
          material_us_patents: 4,
          material_ep_patents: 3,
          patents_with_claims: 6,
          patents_with_family: 7,
          us_patents_with_prosecution_context: 3,
          ep_patents_with_register_context: 2,
          analysis_failures_count: 1,
          failed_sources: ["epo_ops", "lens"],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: ["EP register coverage is incomplete."],
          evidence_warnings: [
            "Verification did not fully pass for one material patent.",
          ],
          search_iterations: 4,
          coverage_summary: {
            queried_source_names: [
              "pubchem",
              "bigquery",
              "surechembl",
              "epo_ops",
              "lens",
            ],
            successful_source_names: ["pubchem", "bigquery", "surechembl"],
            failed_source_names: ["epo_ops", "lens"],
            reviewed_patent_ids: [
              "US1",
              "US2",
              "US3",
              "US4",
              "EP1",
              "EP2",
              "EP3",
            ],
            reviewed_us_patent_ids: ["US1", "US2", "US3", "US4"],
            reviewed_ep_patent_ids: ["EP1", "EP2", "EP3"],
            patents_missing_claims: ["EP3"],
            patents_missing_family_context: [],
            us_patents_missing_prosecution_context: ["US4"],
            ep_patents_missing_register_context: ["EP2"],
            failed_analysis_patent_ids: ["EP3"],
            verification_gaps: [
              "One decisive citation could not be re-validated automatically.",
            ],
          },
          decisive_references: [],
        },
      },
    } as unknown as FTOReport;

    render(<ConfidenceDashboard report={structuredReport} />);

    expect(screen.getByText("LOW")).toBeInTheDocument();
    expect(
      screen.getByText(/7 patents · 3\/3 source providers healthy/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));

    expect(
      screen.getByText(/58 \/ 100 evidence-completeness score/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Verification did not fully pass for one material patent.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing claims text for EP3")).toBeInTheDocument();
  });

  it("surfaces coverage-summary gaps even when no other gap sources exist", () => {
    const coverageGapOnlyReport = {
      ...mockReport,
      clearance_decision: {
        decision: "unclear",
        decision_confidence: 0.8,
        evidence_quality: 0.82,
        decision_reasoning: ["Verification remains incomplete."],
        decision_audit: {
          queried_sources_count: 3,
          successful_sources_count: 3,
          material_patents_reviewed: 6,
          material_us_patents: 4,
          material_ep_patents: 2,
          patents_with_claims: 5,
          patents_with_family: 6,
          us_patents_with_prosecution_context: 4,
          ep_patents_with_register_context: 2,
          analysis_failures_count: 0,
          failed_sources: [],
          evidence_sufficient_for_clearance: false,
          insufficiency_reasons: [],
          evidence_warnings: [],
          search_iterations: 3,
          coverage_summary: {
            queried_source_names: ["pubchem", "bigquery", "surechembl"],
            successful_source_names: ["pubchem", "bigquery", "surechembl"],
            failed_source_names: [],
            reviewed_patent_ids: ["US1", "US2", "US3", "US4", "EP1", "EP2"],
            reviewed_us_patent_ids: ["US1", "US2", "US3", "US4"],
            reviewed_ep_patent_ids: ["EP1", "EP2"],
            patents_missing_claims: ["EP2"],
            patents_missing_family_context: [],
            us_patents_missing_prosecution_context: [],
            ep_patents_missing_register_context: [],
            failed_analysis_patent_ids: [],
            verification_gaps: [
              "One decisive citation still requires manual verification.",
            ],
          },
          decisive_references: [],
        },
      },
    } as unknown as FTOReport;

    render(
      <ConfidenceDashboard report={coverageGapOnlyReport} defaultExpanded />,
    );

    expect(screen.getByText("Known Gaps")).toBeInTheDocument();
    expect(
      screen.getByText(
        "One decisive citation still requires manual verification.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing claims text for EP2")).toBeInTheDocument();
  });
});
