import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import type { FTOReport } from "@praviar/shared-types";
import {
  getSummaryCoveredJurisdictions,
  getSummaryFunnelData,
  getSummaryHasAdditionalConfiguredSources,
} from "@/components/report/summary-tab-helpers";

// Mock heavy child components that are not under test
vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ label }: any) => (
    <div data-testid="molecule-viewer">{label}</div>
  ),
}));

vi.mock("@/components/chemistry/functional-group-badges", () => ({
  FunctionalGroupBadges: ({ groups }: any) => (
    <div data-testid="functional-group-badges">{groups.join(", ")}</div>
  ),
}));

vi.mock("@/components/charts/search-funnel", () => ({
  SearchFunnel: () => <div data-testid="search-funnel">Search Funnel</div>,
}));

vi.mock("@/components/report/design-around-panel", () => ({
  DesignAroundPanel: ({ report: _report }: any) => (
    <div data-testid="design-around-panel">Design Around Panel</div>
  ),
}));

vi.mock("@/components/report/action-items-panel", () => ({
  ActionItemsPanel: ({ report }: any) => (
    <div data-testid="action-items-panel">
      {report.action_items?.length ?? 0} action items
    </div>
  ),
}));

const mockReplace = vi.fn();
let mockSearchParams = "tab=overview&foo=bar";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => new URLSearchParams(mockSearchParams),
}));

import { SummaryTab } from "@/components/report/summary-tab";

describe("SummaryTab data surfacing", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockSearchParams = "tab=overview&foo=bar";
    Object.defineProperty(window, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("renders the summary body as a decision column with a reliability rail", () => {
    const reportWithDecision = {
      ...TEST_REPORT,
      clearance_decision: {
        decision: "unclear",
        decision_confidence: 0.74,
        evidence_quality: 0.68,
        decision_reasoning: [
          "Material fermentation claims need counsel review.",
        ],
        decision_audit: {
          material_patents_reviewed: 8,
          search_iterations: 4,
        },
      },
    } as unknown as FTOReport;

    render(<SummaryTab report={reportWithDecision} />);

    expect(
      screen.getByRole("heading", { name: "Preliminary Review Posture" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Key Risks" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Analysis Summary" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", {
        name: "Report reliability and methodology",
      }),
    ).toBeInTheDocument();
  });

  it("renders each key risk as a fixed evidence-and-counsel docket", () => {
    const reportWithCanonicalBlocker = {
      ...TEST_REPORT,
      clearance_decision: {
        decision: "blocked",
        decision_confidence: 0.9,
        evidence_quality: 0.9,
        decision_reasoning: ["Verified active claim exposure."],
        decision_audit: {
          claim_program_summary: {
            blocking_claim_ids: ["US0000000001A1#claim1"],
            blocking_patent_ids: ["US0000000001A1"],
          },
          blocker_families: [
            {
              schema_version: "blocker-family-v1",
              blocker_id: "bf_0123456789abcdef",
              family_id: "fam-pfizer-1",
              primary_blocking_patent_id: "US0000000001A1",
              material_family_patent_ids: ["US0000000001A1", "WO2020123456A1"],
              blocking_patent_ids: ["US0000000001A1"],
              jurisdictions: ["US"],
              blocking_claims: [
                {
                  claim_id: "US0000000001A1#claim1",
                  patent_id: "US0000000001A1",
                  claim_number: 1,
                  jurisdiction: "US",
                  literal_risk: "high",
                  doe_risk: "low",
                  invalidity_strength: "weak",
                  legal_status: "active",
                  legal_status_provenance_verified: true,
                  prospective_enforceability: "active",
                  accused_acts: ["make", "sell"],
                  accused_acts_verified: true,
                  evidence_sufficient: true,
                  record_basis: [
                    "verified_claim_text",
                    "verified_legal_status",
                  ],
                },
              ],
            },
          ],
        },
      },
    } as unknown as FTOReport;

    render(<SummaryTab report={reportWithCanonicalBlocker} />);

    const firstRisk = within(screen.getByTestId("risk-docket-1"));
    expect(firstRisk.getByText("Patent / family")).toBeInTheDocument();
    expect(
      firstRisk.getByText("Jurisdiction / family scope"),
    ).toBeInTheDocument();
    expect(firstRisk.getByText("Status / accused acts")).toBeInTheDocument();
    expect(firstRisk.getByText("Blocking claims")).toBeInTheDocument();
    expect(firstRisk.getByText("Literal / equivalents")).toBeInTheDocument();
    expect(
      firstRisk.getByText("Invalidity / record basis"),
    ).toBeInTheDocument();
    expect(
      firstRisk.getAllByRole("button", { name: /US0000000001A1/i }),
    ).toHaveLength(2);
    expect(
      firstRisk.getByText(/Claim 1: literal high · DoE low/i),
    ).toBeInTheDocument();
    expect(
      firstRisk.getByText(/Ownership and term are not inferred/i),
    ).toBeInTheDocument();

    fireEvent.click(
      firstRisk.getByRole("button", {
        name: "Open US0000000001A1#claim1 in report evidence",
      }),
    );
    expect(mockReplace).toHaveBeenCalledWith(
      "?tab=claims&foo=bar&patent=US0000000001A1&claim=1",
      { scroll: false },
    );
  });

  it("does not infer blocker identity from legacy narrative text", () => {
    render(<SummaryTab report={TEST_REPORT} />);

    const firstRisk = within(screen.getByTestId("risk-docket-1"));
    expect(
      firstRisk.getByText(/Canonical blocker-family record unavailable/i),
    ).toBeInTheDocument();
    expect(
      firstRisk.queryByRole("button", { name: "US0000000001A1" }),
    ).not.toBeInTheDocument();
  });

  it("keeps compound profile links and disclosures large enough for dense report use", () => {
    render(<SummaryTab report={TEST_REPORT} />);

    const pubChemLink = screen.getByRole("link", {
      name: "Open PubChem CID 1110 in PubChem",
    });
    expect(pubChemLink).toHaveAttribute(
      "href",
      "https://pubchem.ncbi.nlm.nih.gov/compound/1110",
    );
    expect(pubChemLink).toHaveClass(
      "min-h-11",
      "focus-visible:ring-brand-primary/70",
    );

    const showMore = screen.getByRole("button", { name: "Show 2 more" });
    expect(showMore).toHaveClass(
      "min-h-11",
      "focus-visible:ring-brand-primary/70",
    );
    fireEvent.click(showMore);
    expect(screen.getByRole("button", { name: "Show less" })).toHaveClass(
      "min-h-11",
    );
  });

  describe("validation issues warning", () => {
    it("renders validation issues when summary_validation_issues is non-empty", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByText("AI Self-Assessment Issues")).toBeInTheDocument();
      expect(
        screen.getByText(/Two high-risk patents share overlapping claim scope/),
      ).toBeInTheDocument();
    });

    it("does NOT render validation issues when array is empty", () => {
      const reportNoValidation: FTOReport = {
        ...TEST_REPORT,
        risk_summary: {
          ...TEST_REPORT.risk_summary,
          summary_validation_issues: [],
        },
      };

      render(<SummaryTab report={reportNoValidation} />);

      expect(
        screen.queryByText("AI Self-Assessment Issues"),
      ).not.toBeInTheDocument();
    });

    it("does NOT crash when validation issues are omitted", () => {
      const reportNoValidation = {
        ...TEST_REPORT,
        risk_summary: { ...TEST_REPORT.risk_summary },
      } as unknown as FTOReport;
      delete (
        reportNoValidation.risk_summary as Partial<FTOReport["risk_summary"]>
      ).summary_validation_issues;

      render(<SummaryTab report={reportNoValidation} />);

      expect(
        screen.queryByText("AI Self-Assessment Issues"),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Analysis Summary" }),
      ).toBeInTheDocument();
    });
  });

  describe("data integrity warnings", () => {
    it("renders data integrity warning when analysis_failures exist", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(
        screen.getAllByText(/Data integrity warnings/i)[0],
      ).toBeInTheDocument();
      expect(
        screen.getAllByText("Report remains usable with caveats")[0],
      ).toBeInTheDocument();
      expect(
        screen.getAllByText("2 patents failed analysis")[0],
      ).toBeInTheDocument();
    });

    it("surfaces integrity warnings before legal conclusions on small layouts", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      const warning = screen.getAllByText(/Data integrity warnings/i)[0];
      const decision = screen.getByRole("heading", {
        name: "Key Risks",
      });

      expect(
        warning.compareDocumentPosition(decision) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it("opens Coverage & quality details while preserving report URL state", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      const coverageButton = screen.getAllByRole("button", {
        name: /Open coverage details/i,
      })[0];
      expect(coverageButton).toHaveClass("min-h-11");
      fireEvent.click(coverageButton);

      expect(mockReplace).toHaveBeenCalledWith("?tab=meta&foo=bar", {
        scroll: false,
      });
    });

    it("renders data integrity warning when data_limitations exist", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(
        screen.getAllByText("2 data limitations detected")[0],
      ).toBeInTheDocument();
    });

    it("does NOT render data integrity warning when both arrays are empty", () => {
      const reportNoIssues: FTOReport = {
        ...TEST_REPORT,
        analysis_failures: [],
        data_limitations: [],
      };

      render(<SummaryTab report={reportNoIssues} />);

      expect(
        screen.queryByText("Data Integrity Warnings"),
      ).not.toBeInTheDocument();
    });

    it("surfaces persisted critic issues as data-integrity warnings", () => {
      const reportWithCriticIssue: FTOReport = {
        ...TEST_REPORT,
        analysis_failures: [],
        data_limitations: [],
        review_issues: [
          {
            issue_type: "missing_limitation",
            patent_id: "US7582621",
            severity: "major",
            description: "A material limitation needs review.",
          },
        ],
      };

      render(<SummaryTab report={reportWithCriticIssue} />);

      expect(
        screen.getAllByText(/Data integrity warnings/i)[0],
      ).toBeInTheDocument();
      expect(screen.getAllByText("1 critic issue")[0]).toBeInTheDocument();
    });

    it("renders only failures badge when no limitations", () => {
      const reportFailuresOnly: FTOReport = {
        ...TEST_REPORT,
        data_limitations: [],
      };

      render(<SummaryTab report={reportFailuresOnly} />);

      expect(
        screen.getAllByText(/Data integrity warnings/i)[0],
      ).toBeInTheDocument();
      expect(
        screen.getAllByText("2 patents failed analysis")[0],
      ).toBeInTheDocument();
      expect(screen.queryByText(/data limitation/)).not.toBeInTheDocument();
    });

    it("renders only limitations badge when no failures", () => {
      const reportLimitationsOnly: FTOReport = {
        ...TEST_REPORT,
        analysis_failures: [],
      };

      render(<SummaryTab report={reportLimitationsOnly} />);

      expect(
        screen.getAllByText(/Data integrity warnings/i)[0],
      ).toBeInTheDocument();
      expect(
        screen.getAllByText("2 data limitations detected")[0],
      ).toBeInTheDocument();
      expect(screen.queryByText(/failed analysis/)).not.toBeInTheDocument();
    });

    it("fails closed when decision audit says evidence is not clearance-grade", () => {
      const reportScreeningOnly = {
        ...TEST_REPORT,
        analysis_failures: [],
        data_limitations: [],
        clearance_decision: {
          decision: "unclear",
          decision_confidence: 0.62,
          evidence_quality: 0.55,
          decision_reasoning: [],
          decision_audit: {
            queried_sources_count: 4,
            successful_sources_count: 3,
            material_patents_reviewed: 5,
            material_us_patents: 3,
            material_ep_patents: 2,
            patents_with_claims: 4,
            patents_with_family: 5,
            us_patents_with_prosecution_context: 2,
            ep_patents_with_register_context: 1,
            analysis_failures_count: 0,
            failed_sources: [],
            evidence_sufficient_for_clearance: false,
            insufficiency_reasons: ["Missing prosecution context"],
            evidence_warnings: [],
            search_iterations: 2,
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

      render(<SummaryTab report={reportScreeningOnly} />);

      expect(
        screen.getAllByText(
          "Report is screening-only until gaps are reviewed",
        )[0],
      ).toBeInTheDocument();
    });
  });

  describe("DesignAroundPanel rendering", () => {
    it("renders DesignAroundPanel when design_around_suggestions exist on high/medium patents", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByTestId("design-around-panel")).toBeInTheDocument();
    });

    it("does NOT render DesignAroundPanel when no high/medium patents have suggestions", () => {
      const reportNoDesignAround: FTOReport = {
        ...TEST_REPORT,
        patent_analyses: TEST_REPORT.patent_analyses.map((pa) => ({
          ...pa,
          design_around_suggestions: [],
        })),
      };

      render(<SummaryTab report={reportNoDesignAround} />);

      expect(
        screen.queryByTestId("design-around-panel"),
      ).not.toBeInTheDocument();
    });
  });

  describe("key risks section", () => {
    it("renders key risks as standalone section", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByText("Key Risks")).toBeInTheDocument();
    });

    it("shows evidence trail footer", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          (_, element) =>
            element?.tagName === "P" &&
            Boolean(
              element.textContent?.includes("patents analyzed") &&
              element.textContent.includes("source health:"),
            ),
        ),
      ).toBeInTheDocument();
    });

    it("uses normalized healthy source statuses in the evidence trail", () => {
      render(
        <SummaryTab
          report={
            {
              ...TEST_REPORT,
              source_health: {
                entries: [
                  { source: "pubchem", status: "ok" },
                  { source: "lens", status: "success" },
                  { source: "epo", status: "healthy" },
                  { source: "patentsview", status: "available" },
                  { source: "legacy", status: "failed" },
                ],
              },
            } as FTOReport
          }
        />,
      );

      expect(
        screen.getByText(/source health:\s+4\/5 sources\s+\(1 failed/),
      ).toBeInTheDocument();
    });

    it("preserves report URL state when opening a patent from summary", () => {
      const reportWithCanonicalPatent = {
        ...TEST_REPORT,
        clearance_decision: {
          decision: "blocked",
          decision_confidence: 0.9,
          evidence_quality: 0.9,
          decision_reasoning: [],
          decision_audit: {
            claim_program_summary: {
              blocking_claim_ids: ["US0000000001A1#claim1"],
              blocking_patent_ids: ["US0000000001A1"],
            },
            blocker_families: [
              {
                blocker_id: "bf_0123456789abcdef",
                family_id: "fam-pfizer-1",
                primary_blocking_patent_id: "US0000000001A1",
                material_family_patent_ids: ["US0000000001A1"],
                blocking_patent_ids: ["US0000000001A1"],
                jurisdictions: ["US"],
                blocking_claims: [
                  {
                    claim_id: "US0000000001A1#claim1",
                    patent_id: "US0000000001A1",
                    claim_number: 1,
                    jurisdiction: "US",
                    literal_risk: "high",
                    legal_status: "active",
                    legal_status_provenance_verified: true,
                    prospective_enforceability: "active",
                    accused_acts: ["make"],
                    accused_acts_verified: true,
                    evidence_sufficient: true,
                    record_basis: ["verified_claim_text"],
                  },
                ],
              },
            ],
          },
        },
      } as FTOReport;

      render(<SummaryTab report={reportWithCanonicalPatent} />);

      fireEvent.click(
        screen.getByRole("button", {
          name: "Open patent US0000000001A1 in report evidence",
        }),
      );

      expect(mockReplace).toHaveBeenCalledWith(
        "?tab=patents&foo=bar&patent=US0000000001A1",
        { scroll: false },
      );
    });
  });

  describe("action items panel", () => {
    it("renders ActionItemsPanel", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByTestId("action-items-panel")).toBeInTheDocument();
    });
  });

  describe("analysis summary (formerly executive summary)", () => {
    it("renders the analysis summary text", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByText("Analysis Summary")).toBeInTheDocument();
      expect(
        screen.getByText(/This freedom-to-operate analysis evaluated/),
      ).toBeInTheDocument();
    });

    it("opens claim-source evidence for cited summary statements", async () => {
      const reportWithCitedSummary = {
        ...TEST_REPORT,
        risk_summary: {
          ...TEST_REPORT.risk_summary,
          executive_summary:
            "A material claim overlap remains for the lead launch route [1].",
        },
        patent_analyses: [
          {
            ...TEST_REPORT.patent_analyses?.[0],
            patent_id: "US0000000001A1",
            title: "Engineered succinate production route",
          },
        ],
        claim_source_span_map: {
          entries: [
            {
              assertion_id: "assertion-summary-source",
              assertion_text:
                "Claim 1 was assessed against the lead succinate launch route.",
              claim_number: 1,
              customer_visible: true,
              element_number: 1,
              patent_id: "US0000000001A1",
              report_section: "executive_summary",
              source_span_ids: ["span-summary-source"],
              support_status: "supported",
            },
          ],
          spans: {
            "span-summary-source": {
              span_id: "span-summary-source",
              source_type: "element_evidence",
              patent_id: "US0000000001A1",
              claim_number: 1,
              element_number: 1,
              citation: "US0000000001A1 claim 1",
              excerpt:
                "Claim 1 covers recombinant prokaryotic production of succinic acid.",
            },
          },
          unsupported_customer_visible_claim_count: 0,
          needs_review_count: 0,
        },
      } as FTOReport;

      render(<SummaryTab report={reportWithCitedSummary} />);

      fireEvent.click(screen.getByRole("button", { name: "Citation 1" }));

      expect(
        await screen.findByRole("dialog", { name: "Citation source" }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "Claim 1 covers recombinant prokaryotic production of succinic acid.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("Claim 1")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Source: US0000000001A1 claim 1 · Element evidence · Claim 1 · Element 1",
        ),
      ).toBeInTheDocument();
    });

    it("shows high risk warning for high overall risk", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          /Immediate IP\/legal review recommended before commercial development/,
        ),
      ).toBeInTheDocument();
    });

    it("does not show high risk warning for non-high risk", () => {
      const reportLowRisk: FTOReport = {
        ...TEST_REPORT,
        risk_summary: {
          ...TEST_REPORT.risk_summary,
          overall_risk: "low",
        },
      };

      render(<SummaryTab report={reportLowRisk} />);

      expect(
        screen.queryByText(/Immediate attorney review recommended/),
      ).not.toBeInTheDocument();
    });
  });

  describe("compound details", () => {
    it("keeps compound identity visible while methodology is collapsible", () => {
      render(<SummaryTab report={TEST_REPORT} />);

      expect(screen.getByTestId("compound-identity-resolution")).toBeVisible();
      expect(
        screen.getByText("Compound Details & Search Methodology"),
      ).toHaveProperty("tagName", "SPAN");
    });
  });

  describe("methodology funnel data", () => {
    it("coerces missing audit counts to zero", () => {
      const reportWithoutAudit = {
        ...TEST_REPORT,
        audit_trail: undefined,
      } as FTOReport;

      expect(getSummaryFunnelData(reportWithoutAudit)).toEqual([
        { stage: "Discovered", count: 0 },
        { stage: "After Hard Filter", count: 0 },
        { stage: "After Ranking", count: 0 },
        { stage: "After Triage", count: 0 },
        { stage: "Analyzed", count: 0 },
      ]);
    });
  });

  describe("source coverage helper semantics", () => {
    it("does not inflate direct jurisdiction counts from configured datasets", () => {
      const configuredSourceReport = {
        ...TEST_REPORT,
        source_health: {
          entries: [
            {
              source: "bigquery",
              status: "ok",
              patent_count: 10,
              error_message: "",
            },
            {
              source: "patentscope",
              status: "ok",
              patent_count: 12,
              error_message: "",
            },
          ],
        },
      } as FTOReport;

      expect(getSummaryCoveredJurisdictions(configuredSourceReport)).toBe(0);
      expect(
        getSummaryHasAdditionalConfiguredSources(configuredSourceReport),
      ).toBe(true);
    });

    it("counts exact jurisdiction sources as direct coverage", () => {
      const directReport = {
        ...TEST_REPORT,
        source_health: {
          entries: [
            {
              source: "epo_search",
              status: "ok",
              patent_count: 25,
              error_message: "",
            },
            {
              source: "kipris",
              status: "ok",
              patent_count: 8,
              error_message: "",
            },
          ],
        },
      } as FTOReport;

      expect(getSummaryCoveredJurisdictions(directReport)).toBe(6);
    });
  });
});
