import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import type {
  FTOReport,
  InvalidityAssessment,
  PriorArtReference,
  ClaimChart,
  ClaimChartEntry,
  GrahamFactors,
} from "@praviar/shared-types";

import { InvalidityTab } from "@/components/report/invalidity-tab";

// ---------------------------------------------------------------------------
// Test data builders
// ---------------------------------------------------------------------------

function makePriorArt(
  overrides: Partial<PriorArtReference> = {},
): PriorArtReference {
  return {
    reference_id: "REF-001",
    title: "Synthesis of dicarboxylic acids via microbial fermentation",
    publication_date: "2018-06-15",
    relevance: "Directly anticipates claim 1",
    anticipation_score: 0.82,
    obviousness_score: 0.75,
    reference_type: "journal_article",
    authors: ["Smith, J.", "Lee, K."],
    journal: "J. Organic Chemistry",
    doi: "10.1234/joc.2018.001",
    url: "https://doi.org/10.1234/joc.2018.001",
    abstract: "We describe a method...",
    source_database: "semantic_scholar",
    ...overrides,
  };
}

function makeClaimChartEntry(
  overrides: Partial<ClaimChartEntry> = {},
): ClaimChartEntry {
  return {
    element_number: 1,
    element_text: "A fermentation step using E. coli",
    prior_art_reference_id: "REF-001",
    prior_art_disclosure:
      "Smith describes E. coli fermentation at paragraph [0042]",
    citation_location: "Col. 4, lines 15-30",
    disclosed: "yes",
    notes: "",
    ...overrides,
  };
}

function makeClaimChart(overrides: Partial<ClaimChart> = {}): ClaimChart {
  return {
    patent_id: "US0000000001A1",
    claim_number: 1,
    prior_art_reference_id: "REF-001",
    entries: [
      makeClaimChartEntry({ element_number: 1, disclosed: "yes" }),
      makeClaimChartEntry({
        element_number: 2,
        disclosed: "partial",
        element_text: "a purification step",
      }),
      makeClaimChartEntry({
        element_number: 3,
        disclosed: "no",
        element_text: "yield above 90%",
      }),
    ],
    all_elements_disclosed: false,
    chart_summary:
      "Two of three elements disclosed; yield limitation not anticipated.",
    ...overrides,
  };
}

function makeGrahamFactors(): GrahamFactors {
  return {
    scope_and_content:
      "The prior art teaches succinic acid production via bacterial fermentation.",
    differences_from_prior_art:
      "The claimed process uses a specific E. coli strain not taught in prior art.",
    level_of_ordinary_skill:
      "PhD-level biochemist with 5 years fermentation experience.",
    commercial_success: "Commercial adoption of bio-succinic acid is growing.",
    long_felt_need:
      "Industry has sought cost-effective bio-based succinic acid production for decades.",
    failure_of_others:
      "Multiple companies attempted similar processes without success.",
    unexpected_results: "Yield exceeds theoretical predictions.",
    overall_obviousness_assessment:
      "Moderate case for obviousness given differences in strain engineering.",
  };
}

function makeInvalidityAssessment(
  overrides: Partial<InvalidityAssessment> = {},
): InvalidityAssessment {
  return {
    patent_id: "US0000000001A1",
    claim_numbers: [1, 2],
    ptab: {
      has_been_challenged: true,
      proceedings: [
        {
          proceeding_number: "IPR2024-00123",
          type: "IPR",
          status: "Final Decision",
          filing_date: "2024-01-15",
          decision_date: "2025-01-15",
          claims_challenged: [1, 2, 3],
          claims_cancelled: [3],
          claims_survived: [1, 2],
          outcome_summary: "Claims 1-2 survived; claim 3 cancelled.",
        },
      ],
      all_claims_cancelled: [3],
    },
    prior_art: [
      makePriorArt(),
      makePriorArt({
        reference_id: "REF-002",
        title: "Biorefinery approaches for C4 acids",
        publication_date: "2015-03-20",
        anticipation_score: 0.55,
        obviousness_score: 0.68,
        reference_type: "patent",
        source_database: "openalex",
      }),
    ],
    written_description_issues: [
      "Genus claim recites broad class of microorganisms but only exemplifies E. coli.",
    ],
    claim_charts: [makeClaimChart()],
    graham_factors: makeGrahamFactors(),
    enablement_screening: {
      genus_claim_detected: true,
      genus_indicators: [
        "broad microorganism genus",
        "unlimited substrate scope",
      ],
      specification_enables_full_scope: "no",
      amgen_v_sanofi_flags: [
        "Functional claim language without structural guidance",
      ],
      reasoning:
        "Specification only enables E. coli strains but claims extend to all bacteria.",
    },
    overall_invalidity_strength: "Moderate",
    reasoning:
      "Some prior art anticipates key elements; enablement concerns present.",
    confidence: 0.72,
    confidence_band: "MODERATE",
    screening_disclaimer: "This is an automated screening only.",
    ...overrides,
  };
}

function makeMockReport(overrides: Partial<FTOReport> = {}): FTOReport {
  return {
    report_id: "rpt-001",
    generated_at: "2026-03-12T10:00:00Z",
    praviar_pipeline_version: "0.9.0",
    compound: {
      name: "Succinic acid",
      canonical_smiles: "OC(=O)CCC(O)=O",
      inchi: "InChI=1S/C4H6O4",
      inchi_key: "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
      pubchem_cid: 1110,
      synonyms: [],
      cas_numbers: [],
      molecular_formula: "C4H6O4",
      molecular_weight: 118.09,
      morgan_fp: "",
      maccs_keys: "",
      functional_groups: [],
      related_compounds: [],
      original_input: "succinic acid",
      input_type: "name",
    },
    risk_summary: {
      overall_risk: "medium",
      blocking_patents_count: 1,
      total_patents_analyzed: 1,
      key_risks: [],
      executive_summary: "",
      summary_validation_issues: [],
    },
    patent_analyses: [],
    doe_assessments: [],
    invalidity_assessments: [makeInvalidityAssessment()],
    verification: {
      checks: [],
      all_citations_valid: true,
      all_claims_grounded: true,
      all_entities_valid: true,
      dates_consistent: true,
      risk_levels_justified: true,
      issues: [],
    },
    analysis_failures: [],
    data_limitations: [],
    total_patents_found: 100,
    patents_after_triage: 10,
    search_sources_used: [],
    source_health: { entries: [] },
    scholarly_prior_art_count: 5,
    audit_trail: {
      search_funnel: [],
      triage_audit: [],
      analysis_audit: [],
      timing_data: [],
      total_patents_discovered: 100,
      patents_after_hard_filter: 80,
      patents_after_ranking: 30,
      patents_after_triage: 10,
      patents_analyzed: 1,
    },
    patent_narratives: {},
    disclaimer: "",
    llm_models_used: {},
    total_input_tokens: 50000,
    total_output_tokens: 3000,
    estimated_cost_usd: 3.0,
    step_token_usage: [],
    ...overrides,
  };
}

describe("InvalidityTab", () => {
  it("renders patent ID for each invalidity assessment", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("US0000000001A1")).toBeInTheDocument();
  });

  it("renders overall invalidity strength badge", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Moderate")).toBeInTheDocument();
  });

  it("renders confidence band badge", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("MODERATE")).toBeInTheDocument();
  });

  it("renders reasoning text", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(
      screen.getByText(
        "Some prior art anticipates key elements; enablement concerns present.",
      ),
    ).toBeInTheDocument();
  });

  it("renders PTAB proceedings table", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("PTAB Proceedings")).toBeInTheDocument();
    const ptabRegion = screen.getByRole("region", {
      name: "Invalidity PTAB proceedings table",
    });
    expect(ptabRegion).toHaveClass(
      "overflow-x-auto",
      "[scrollbar-gutter:stable]",
    );
    expect(ptabRegion.querySelector("table")).toHaveClass("md:min-w-[920px]");
    expect(
      Array.from(ptabRegion.querySelectorAll("tbody td")).every((cell) =>
        cell.classList.contains("md:align-top"),
      ),
    ).toBe(true);
    expect(screen.getByText("IPR2024-00123")).toBeInTheDocument();
    expect(screen.getByText("IPR")).toBeInTheDocument();
    expect(screen.getByText("Final Decision")).toBeInTheDocument();
    expect(screen.getByText("2024-01-15")).toBeInTheDocument();
    expect(screen.getByText("2025-01-15")).toBeInTheDocument();
    expect(
      screen.getByText("Claims 1-2 survived; claim 3 cancelled."),
    ).toBeInTheDocument();
  });

  it("renders mobile-readable PTAB row labels", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Proceeding type")).toBeInTheDocument();
    expect(screen.getByText("Claims challenged")).toBeInTheDocument();
    expect(screen.getByText("Claims cancelled")).toBeInTheDocument();
  });

  it("renders prior art references table with scores as percentages", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Prior Art References")).toBeInTheDocument();
    const priorArtRegion = screen.getByRole("region", {
      name: "Invalidity prior art references table for US0000000001A1",
    });
    expect(priorArtRegion).toHaveClass(
      "overflow-x-auto",
      "[scrollbar-gutter:stable]",
    );
    expect(priorArtRegion.querySelector("table")).toHaveClass(
      "md:min-w-[860px]",
    );
    expect(screen.getByText("REF-001")).toBeInTheDocument();
    expect(screen.getByText("REF-002")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Synthesis of dicarboxylic acids via microbial fermentation",
      ).length,
    ).toBeGreaterThanOrEqual(1);
    // 0.82 -> 82%
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    // REF-002: 0.55 -> 55%, 0.68 -> 68%
    expect(screen.getByText("55%")).toBeInTheDocument();
    expect(screen.getByText("68%")).toBeInTheDocument();
  });

  it("gives every prior art table a unique patent-specific region name", () => {
    render(
      <InvalidityTab
        report={makeMockReport({
          invalidity_assessments: [
            makeInvalidityAssessment(),
            makeInvalidityAssessment({
              patent_id: "EP3456789B1",
              claim_charts: [],
            }),
          ],
        })}
      />,
    );

    expect(
      screen.getByRole("region", {
        name: "Invalidity prior art references table for US0000000001A1",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Invalidity prior art references table for EP3456789B1",
      }),
    ).toBeInTheDocument();
  });

  it("renders prior art references with mobile scan labels", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getAllByText("Anticipation")).toHaveLength(2);
    expect(screen.getAllByText("Obviousness")).toHaveLength(2);
    expect(screen.getAllByText("Source database")).toHaveLength(2);
  });

  it("renders prior art reference types as badges", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("journal_article")).toBeInTheDocument();
    expect(screen.getByText("patent")).toBeInTheDocument();
  });

  it("renders claim charts with element disclosure indicators", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Claim Charts")).toBeInTheDocument();
    const claimChartRegion = screen.getByRole("region", {
      name: "Claim chart rows for US0000000001A1 claim 1",
    });
    expect(claimChartRegion).toHaveClass(
      "overflow-x-auto",
      "[scrollbar-gutter:stable]",
    );
    expect(claimChartRegion.querySelector("table")).toHaveClass(
      "md:min-w-[900px]",
    );
    expect(screen.getByText(/Claim 1 vs REF-001/)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getAllByText(
        "Synthesis of dicarboxylic acids via microbial fermentation",
      ).length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen
        .getAllByText(
          "Synthesis of dicarboxylic acids via microbial fermentation",
        )
        .some((element) =>
          element.classList.contains("[overflow-wrap:anywhere]"),
        ),
    ).toBe(true);
    const sourceLink = screen.getByLabelText(
      "Open source for US0000000001A1 claim 1 element 1 via REF-001",
    );
    expect(sourceLink).toHaveAttribute(
      "href",
      "https://doi.org/10.1234/joc.2018.001",
    );
    expect(sourceLink).toHaveClass("min-h-11");
    // Chart summary
    expect(
      screen.getByText(
        "Two of three elements disclosed; yield limitation not anticipated.",
      ),
    ).toBeInTheDocument();
  });

  it("retains textual prior-art citation while suppressing an unsafe source link", () => {
    const hostileReference = makePriorArt({
      doi: "10.1234/safe-fallback-must-not-mask-hostile-url",
      url: "javascript:alert(document.domain)",
    });
    render(
      <InvalidityTab
        report={makeMockReport({
          invalidity_assessments: [
            makeInvalidityAssessment({
              prior_art: [hostileReference],
              claim_charts: [makeClaimChart()],
            }),
          ],
        })}
      />,
    );

    expect(
      screen.queryByLabelText(
        "Open source for US0000000001A1 claim 1 element 1 via REF-001",
      ),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("No source link").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "Smith describes E. coli fermentation at paragraph [0042]",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "Synthesis of dicarboxylic acids via microbial fermentation",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders claim chart entries with mobile evidence labels", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getAllByText("Claim element")).toHaveLength(3);
    expect(screen.getAllByText("Prior art disclosure")).toHaveLength(3);
    expect(screen.getAllByText("Citation location")).toHaveLength(3);
    expect(screen.getAllByText("Evidence packet")).toHaveLength(3);
  });

  it("copies a claim chart row packet with report provenance", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<InvalidityTab report={makeMockReport()} />);

    const copyControl = screen.getByTestId(
      "claim-chart-copy-US0000000001A1-1-1",
    );
    expect(copyControl).toHaveClass("min-h-11");
    await act(async () => {
      fireEvent.click(copyControl);
    });

    expect(writeText).toHaveBeenCalledTimes(1);
    const packet = writeText.mock.calls[0][0] as string;
    expect(packet).toContain("Praviar claim chart row packet");
    expect(packet).toContain("Report: rpt-001");
    expect(packet).toContain("Generated: 2026-03-12T10:00:00Z");
    expect(packet).toContain("Pipeline: 0.9.0");
    expect(packet).toContain("Patent: US0000000001A1");
    expect(packet).toContain("Claim: 1");
    expect(packet).toContain("Prior art reference: REF-001");
    expect(packet).toContain(
      "Prior art title: Synthesis of dicarboxylic acids via microbial fermentation",
    );
    expect(packet).toContain("Authors: Smith, J., Lee, K.");
    expect(packet).toContain("Published: 2018-06-15");
    expect(packet).toContain("Reference type: journal_article");
    expect(packet).toContain("Source database: semantic_scholar");
    expect(packet).toContain("DOI: 10.1234/joc.2018.001");
    expect(packet).toContain(
      "Source URL: https://doi.org/10.1234/joc.2018.001",
    );
    expect(packet).toContain("Element: 1");
    expect(packet).toContain("Disclosure posture: Disclosed");
    expect(packet).toContain("Citation location: Col. 4, lines 15-30");
    expect(packet).toContain(
      "Guardrail: Automated invalidity screening is not a legal opinion",
    );
    expect(screen.getByText("Copied")).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "Copy packet for US0000000001A1 claim 1 element 1 vs REF-001",
      ),
    ).toBeInTheDocument();
  });

  it("shows a claim chart copy failure state when clipboard access is blocked", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<InvalidityTab report={makeMockReport()} />);

    await act(async () => {
      fireEvent.click(
        screen.getByTestId("claim-chart-copy-US0000000001A1-1-1"),
      );
    });

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Copy unavailable")).toBeInTheDocument();
    const manualPacket = screen.getByLabelText(
      "Manual packet text for US0000000001A1 claim 1 element 1",
    ) as HTMLTextAreaElement;
    expect(manualPacket).toHaveClass("w-full", "min-w-0", "max-w-full");
    expect(manualPacket.value).toContain("Praviar claim chart row packet");
  });

  it("renders Graham Factors section and expands on click", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    const grahamButton = screen.getByText("Graham Factors");
    expect(grahamButton).toBeInTheDocument();
    // Collapsed by default — content should not be visible
    expect(screen.queryByText("Scope & Content")).not.toBeInTheDocument();
    // Click to expand
    fireEvent.click(grahamButton);
    expect(screen.getByText("Scope & Content")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The prior art teaches succinic acid production via bacterial fermentation.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Overall Obviousness")).toBeInTheDocument();
  });

  it("renders enablement screening flags", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Enablement Screening Flags")).toBeInTheDocument();
    expect(screen.getByText("broad microorganism genus")).toBeInTheDocument();
    expect(screen.getByText("unlimited substrate scope")).toBeInTheDocument();
    expect(
      screen.getByText("Functional claim language without structural guidance"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Specification only enables E. coli strains but claims extend to all bacteria.",
      ),
    ).toBeInTheDocument();
  });

  it("renders written description issues", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(screen.getByText("Written Description Issues")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Genus claim recites broad class of microorganisms but only exemplifies E. coli.",
      ),
    ).toBeInTheDocument();
  });

  it("renders screening disclaimer", () => {
    render(<InvalidityTab report={makeMockReport()} />);
    expect(
      screen.getByText("This is an automated screening only."),
    ).toBeInTheDocument();
  });

  it("gives each prior-art table landmark a patent-specific name", () => {
    render(
      <InvalidityTab
        report={makeMockReport({
          invalidity_assessments: [
            makeInvalidityAssessment({ patent_id: "US0000000001A1" }),
            makeInvalidityAssessment({ patent_id: "EP4455667B1" }),
          ],
        })}
      />,
    );

    expect(
      screen.getByRole("region", {
        name: "Invalidity prior art references table for US0000000001A1",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Invalidity prior art references table for EP4455667B1",
      }),
    ).toBeInTheDocument();
  });

  it("shows empty state when no invalidity assessments exist", () => {
    const report = makeMockReport({ invalidity_assessments: [] });
    render(<InvalidityTab report={report} />);
    expect(
      screen.getByText("Invalidity has not been assessed"),
    ).toBeInTheDocument();
  });

  it("does not render PTAB section when patent has not been challenged", () => {
    const report = makeMockReport({
      invalidity_assessments: [
        makeInvalidityAssessment({
          ptab: {
            has_been_challenged: false,
            proceedings: [],
            all_claims_cancelled: [],
          },
        }),
      ],
    });
    render(<InvalidityTab report={report} />);
    expect(screen.queryByText("PTAB Proceedings")).not.toBeInTheDocument();
  });

  it("does not render enablement screening when genus claim not detected", () => {
    const report = makeMockReport({
      invalidity_assessments: [
        makeInvalidityAssessment({
          enablement_screening: {
            genus_claim_detected: false,
            genus_indicators: [],
            specification_enables_full_scope: "yes",
            amgen_v_sanofi_flags: [],
            reasoning: "",
          },
        }),
      ],
    });
    render(<InvalidityTab report={report} />);
    expect(
      screen.queryByText("Enablement Screening Flags"),
    ).not.toBeInTheDocument();
  });
});
