import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { TEST_REPORT } from "../fixtures/report-fixture";
import type { FTOReport } from "@praviar/shared-types";

// Mock chart components that depend on Recharts
vi.mock("@/components/charts/timing-waterfall", () => ({
  TimingWaterfall: () => (
    <div data-testid="timing-waterfall">Timing Waterfall</div>
  ),
}));

vi.mock("@/components/charts/usage-chart", () => ({
  UsageChart: () => <div data-testid="usage-chart">Usage Chart</div>,
}));

import { MetaTab } from "@/components/report/meta-tab";

describe("MetaTab", () => {
  describe("quality and provenance summary", () => {
    it("shows report-level factual accuracy with the correct reliance boundary", () => {
      render(
        <MetaTab report={{ ...TEST_REPORT, factual_accuracy_rate: 0.97 }} />,
      );

      expect(screen.getByText("97%")).toBeInTheDocument();
      expect(
        screen.getByText(/distinct from claim-mapping confidence/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/does not measure omissions/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/not a legal-accuracy score/),
      ).toBeInTheDocument();
    });

    it("does not turn an absent factual-accuracy field into zero", () => {
      render(
        <MetaTab
          report={{ ...TEST_REPORT, factual_accuracy_rate: undefined }}
        />,
      );

      const accuracyMetric = screen
        .getByText("Factual accuracy")
        .closest("div");
      expect(accuracyMetric).toHaveTextContent("Not reported");
      expect(accuracyMetric).not.toHaveTextContent("0%");
    });

    it("labels synthetic fixture evidence as wiring proof only", () => {
      const report = {
        ...TEST_REPORT,
        data_limitations: [],
        factual_accuracy_rate: 0.97,
        claim_source_span_map: {
          generated_from: "dev_seed_fixture",
          entries: [],
          spans: {},
        },
      } as unknown as FTOReport;

      render(<MetaTab report={report} />);

      expect(
        screen.getByText("Synthetic evidence fixture"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/proves persisted API, database, and UI wiring only/),
      ).toBeInTheDocument();
      expect(screen.getByText(/not production-corpus/)).toBeInTheDocument();
      expect(
        screen.getByText("Fixture declares no data limitations"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/not evidence of production-corpus completeness/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("No data limitations detected"),
      ).not.toBeInTheDocument();
    });
  });

  describe("analysis failures table", () => {
    it("renders critic review issues with severity and correction", () => {
      render(
        <MetaTab
          report={{
            ...TEST_REPORT,
            review_issues: [
              {
                issue_type: "missing_limitation",
                patent_id: "US7582621",
                severity: "major",
                description: "A material limitation needs review.",
                suggested_correction: "Re-check claim 1 against the source.",
              },
            ],
          }}
        />,
      );

      expect(screen.getByText("Critic Review Issues")).toBeInTheDocument();
      expect(screen.getByText("US7582621")).toBeInTheDocument();
      expect(screen.getByText("Missing Limitation")).toBeInTheDocument();
      expect(
        screen.getByText("Re-check claim 1 against the source."),
      ).toBeInTheDocument();
    });

    it("renders analysis failures table when failures exist", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Analysis Failures")).toBeInTheDocument();
      // TEST_REPORT has 2 analysis failures
      expect(screen.getByText("US0000000005A1")).toBeInTheDocument();
      expect(screen.getByText("US0000000008A1")).toBeInTheDocument();
      expect(
        screen.getByRole("region", {
          name: "Analysis failures horizontal scroll area",
        }),
      ).toHaveAttribute("tabindex", "0");
    });

    it("shows failure step information", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Step 4: Analyze")).toBeInTheDocument();
      expect(screen.getByText("Step 5: Doe")).toBeInTheDocument();
    });

    it("shows safe recovery categories", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Validation issue")).toBeInTheDocument();
      expect(screen.getByText("Source timeout")).toBeInTheDocument();
    });

    it("shows recovery notes without raw backend diagnostics", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(
        screen.getByText(/Generated analysis failed report-shape checks/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/External evidence retrieval did not finish/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("ClaudeValidationError"),
      ).not.toBeInTheDocument();
      expect(screen.queryByText("TimeoutError")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/LLM response failed schema validation/),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/USPTO file wrapper API timed out/),
      ).not.toBeInTheDocument();
    });

    it("sanitizes secrets from failure and limitation diagnostics", () => {
      const reportWithSecrets = {
        ...TEST_REPORT,
        analysis_failures: [
          {
            patent_id: "US9999999B2",
            step: "step4_analyze",
            error_type: "RuntimeError",
            error_message:
              "postgres://secret-host/praviar sk_live_abc123 SELECT * FROM analyses Traceback most recent call",
            recoverable: false,
          },
        ],
        data_limitations: [
          {
            category: "source_unavailable",
            description:
              "postgres://secret-host/praviar sk_live_abc123 SELECT * FROM analyses Traceback most recent call",
            impact:
              "Retry failed at /Users/private/project with Bearer topsecretvalue",
          },
        ],
        source_health: {
          entries: [
            {
              source: "patcid",
              status: "failed",
              patent_count: 0,
              error_message:
                "postgres://secret-host/praviar sk_live_abc123 SELECT * FROM analyses",
            },
          ],
        },
      } as unknown as FTOReport;

      render(<MetaTab report={reportWithSecrets} />);

      expect(screen.queryByText(/secret-host/)).not.toBeInTheDocument();
      expect(screen.queryByText(/sk_live_/)).not.toBeInTheDocument();
      expect(screen.queryByText(/SELECT \*/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
      expect(
        screen.queryByText(/Bearer topsecretvalue/),
      ).not.toBeInTheDocument();
      expect(screen.getAllByText(/redacted/i).length).toBeGreaterThan(0);
    });

    it("shows failure count badge", () => {
      render(<MetaTab report={TEST_REPORT} />);

      // Both failures badge and limitations badge show "2"
      const badges = screen.getAllByText("2");
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });

    it("renders 'All patents processed successfully' when no failures", () => {
      const reportNoFailures: FTOReport = {
        ...TEST_REPORT,
        analysis_failures: [],
      };

      render(<MetaTab report={reportNoFailures} />);

      expect(
        screen.getByText("All patents processed successfully"),
      ).toBeInTheDocument();
    });

    it("does not crash when optional integrity arrays are absent", () => {
      const partialReport = {
        ...TEST_REPORT,
        analysis_failures: undefined,
        data_limitations: undefined,
      } as unknown as FTOReport;

      render(<MetaTab report={partialReport} />);

      expect(
        screen.getByText("All patents processed successfully"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Fixture declares no data limitations"),
      ).toBeInTheDocument();
    });

    it("fails closed when report failure counts disagree", () => {
      const inconsistentReport = {
        ...TEST_REPORT,
        analysis_failures: [],
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
            analysis_failures_count: 1,
            failed_sources: [],
            evidence_sufficient_for_clearance: true,
            insufficiency_reasons: [],
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
              failed_analysis_patent_ids: ["US9999999B2"],
              verification_gaps: [],
            },
            decisive_references: [],
          },
        },
      } as unknown as FTOReport;

      render(<MetaTab report={inconsistentReport} />);

      expect(
        screen.getByText("Report metadata inconsistency"),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("All patents processed successfully"),
      ).not.toBeInTheDocument();
    });
  });

  describe("data limitations cards", () => {
    it("renders data limitations cards when limitations exist", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Data Limitations")).toBeInTheDocument();
      expect(screen.getByText("Source Unavailable")).toBeInTheDocument();
      expect(screen.getByText("Enrichment Gap")).toBeInTheDocument();
    });

    it("shows limitation descriptions", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(
        screen.getByText(/PatCID API returned 503 Service Unavailable/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/BigQuery annotations quota exceeded/),
      ).toBeInTheDocument();
    });

    it("shows limitation impact", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          /Structurally similar patents found only via SureChEMBL/,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/CPC code enrichment relied on EPO data only/),
      ).toBeInTheDocument();
    });

    it("keeps the fixture reliance boundary when no limitations are listed", () => {
      const reportNoLimitations: FTOReport = {
        ...TEST_REPORT,
        data_limitations: [],
      };

      render(<MetaTab report={reportNoLimitations} />);

      expect(
        screen.getByText("Fixture declares no data limitations"),
      ).toBeInTheDocument();
    });
  });

  describe("verification checks severity icons", () => {
    it("renders verification checks table", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Verification")).toBeInTheDocument();
      expect(
        screen.getByRole("region", {
          name: "Verification checks horizontal scroll area",
        }),
      ).toHaveAttribute("tabindex", "0");
    });

    it("shows check names in verification table", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("citation_validity")).toBeInTheDocument();
      expect(screen.getByText("claim_grounding")).toBeInTheDocument();
      expect(screen.getByText("entity_validation")).toBeInTheDocument();
      expect(screen.getByText("date_consistency")).toBeInTheDocument();
      expect(screen.getByText("risk_level_justification")).toBeInTheDocument();
      expect(screen.getByText("doe_consistency")).toBeInTheDocument();
    });

    it("shows check details", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(
        screen.getByText(
          /The fictional report references are internally consistent/,
        ),
      ).toBeInTheDocument();
    });

    it("redacts raw verification diagnostics", () => {
      const report = {
        ...TEST_REPORT,
        verification: {
          ...TEST_REPORT.verification,
          checks: [
            {
              ...TEST_REPORT.verification.checks[0],
              details:
                "Bearer abc123 postgres://secret SELECT * FROM checks Traceback boom",
            },
          ],
        },
      } as FTOReport;

      render(<MetaTab report={report} />);

      expect(
        screen.getByText(/\[redacted connection string\]/),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Bearer abc123/)).not.toBeInTheDocument();
      expect(screen.queryByText(/postgres:\/\/secret/)).not.toBeInTheDocument();
      expect(screen.queryByText(/SELECT \*/)).not.toBeInTheDocument();
    });

    it("shows pass severity icon (green check) for passing checks", () => {
      const { container } = render(<MetaTab report={TEST_REPORT} />);

      // Passing checks should have green-500 icons
      const greenIcons = container.querySelectorAll(".text-success");
      // 5 passing verification checks + 5 summary flags that pass + check icon for no-failures-header
      expect(greenIcons.length).toBeGreaterThanOrEqual(5);
    });

    it("shows warning severity icon (amber triangle) for warning checks", () => {
      const { container } = render(<MetaTab report={TEST_REPORT} />);

      // doe_consistency has severity "warning"
      const amberIcons = container.querySelectorAll(".text-warning");
      expect(amberIcons.length).toBeGreaterThanOrEqual(1);
    });

    it("exposes verification outcomes as text instead of color and icons alone", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Warning").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Passed:/).length).toBeGreaterThan(0);
    });

    it("renders verification summary flags", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("All Citations Valid")).toBeInTheDocument();
      expect(screen.getByText("All Claims Grounded")).toBeInTheDocument();
      expect(screen.getByText("All Entities Valid")).toBeInTheDocument();
      expect(screen.getByText("Dates Consistent")).toBeInTheDocument();
      expect(screen.getByText("Risk Levels Justified")).toBeInTheDocument();
    });
  });

  describe("report metadata", () => {
    it("displays report_id", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Report ID")).toBeInTheDocument();
      expect(screen.getByText("rpt_demo_succinic_001")).toBeInTheDocument();
    });

    it("displays version", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Version")).toBeInTheDocument();
      expect(screen.getByText("0.9.4")).toBeInTheDocument();
    });

    it("displays generated_at date", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Generated")).toBeInTheDocument();
      // formatDate should render something containing 2026
      const generated = screen.getByText(/2026/);
      expect(generated).toBeInTheDocument();
    });

    it("keeps long review engine identifiers scrollable and wrapped", () => {
      const longModelId =
        "anthropic.claude-3-7-sonnet-20260219-with-extended-thinking-and-production-gated-evidence-routing";
      const report = {
        ...TEST_REPORT,
        llm_models_used: {
          extremely_long_specialist_review_role_name_without_spaces:
            longModelId,
        },
      } satisfies FTOReport;

      render(<MetaTab report={report} />);

      const enginesRegion = screen.getByRole("region", {
        name: "Review engines horizontal scroll area",
      });
      expect(enginesRegion).toHaveClass("overflow-x-auto");
      expect(within(enginesRegion).getByRole("table")).toHaveClass(
        "min-w-[24rem]",
      );
      expect(
        screen.getByText(
          "extremely_long_specialist_review_role_name_without_spaces",
        ),
      ).toHaveClass("[overflow-wrap:anywhere]");
      expect(screen.getByText(longModelId)).toHaveClass(
        "break-all",
        "[overflow-wrap:anywhere]",
      );
    });
  });

  describe("analysis effort card", () => {
    it("displays effort counts with report-facing labels", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Evidence Context")).toBeInTheDocument();
      expect(screen.getByText("Review Output")).toBeInTheDocument();
      expect(screen.getByText("Total Effort")).toBeInTheDocument();
      expect(screen.queryByText("Input Tokens")).not.toBeInTheDocument();
      expect(screen.queryByText("Output Tokens")).not.toBeInTheDocument();
      expect(screen.queryByText("Total Tokens")).not.toBeInTheDocument();
    });

    it("renders not-reported effort states when token totals are absent", () => {
      const report = { ...TEST_REPORT } as Partial<FTOReport>;
      delete report.total_input_tokens;
      delete report.total_output_tokens;

      render(<MetaTab report={report as FTOReport} />);

      expect(screen.getAllByText("Not reported")).toHaveLength(4);
      expect(screen.queryByText(/NaNk/i)).not.toBeInTheDocument();
    });

    it("does not display cost (cost removed from UI)", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.queryByText("Estimated Cost")).not.toBeInTheDocument();
    });
  });

  describe("review engines table", () => {
    it("displays review engines table", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("Review Engines")).toBeInTheDocument();
      expect(screen.queryByText("Models Used")).not.toBeInTheDocument();
    });

    it("shows model roles", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(screen.getByText("triage")).toBeInTheDocument();
      expect(screen.getByText("analysis")).toBeInTheDocument();
    });
  });

  describe("disclaimer", () => {
    it("renders disclaimer when present", () => {
      render(<MetaTab report={TEST_REPORT} />);

      expect(
        screen.getByText(/SYNTHETIC COMPONENT-TEST FIXTURE/),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Synthetic evidence fixture"),
      ).toBeInTheDocument();
    });

    it("does not render disclaimer when absent", () => {
      const reportNoDisclaimer: FTOReport = {
        ...TEST_REPORT,
        disclaimer: "",
      };

      render(<MetaTab report={reportNoDisclaimer} />);

      expect(
        screen.queryByText(/SYNTHETIC COMPONENT-TEST FIXTURE/),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText("No synthetic marker detected"),
      ).toBeInTheDocument();
    });
  });
});
