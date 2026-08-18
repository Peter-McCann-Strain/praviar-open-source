import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type {
  FTOReport,
  PatentAnalysis,
  ClaimAnalysis,
  ClaimElement,
} from "@praviar/shared-types";

// Mock the ClaimElementRow to make tests focused on ClaimsTab logic
vi.mock("@/components/patent/claim-element-row", () => ({
  ClaimElementRow: ({
    element,
    doeAssessment,
    patentId,
    reportCitation,
    sourceSpan,
    sourceSupport,
  }: any) => (
    <div data-testid={`claim-element-${element.element_number}`}>
      Element {element.element_number}: {element.status}
      {doeAssessment && (
        <span data-testid={`doe-attached-${element.element_number}`}>
          DoE attached
        </span>
      )}
      {reportCitation?.reportId && (
        <span data-testid={`report-citation-${element.element_number}`}>
          {reportCitation.reportId}:{reportCitation.pipelineVersion}
        </span>
      )}
      {patentId && (
        <span data-testid={`row-patent-${element.element_number}`}>
          {patentId}
        </span>
      )}
      {sourceSupport && (
        <span data-testid={`source-support-${element.element_number}`}>
          {sourceSupport.support_status}:{sourceSupport.assertion_id}
        </span>
      )}
      {sourceSpan && (
        <span data-testid={`source-span-${element.element_number}`}>
          {sourceSpan.span_id}:{sourceSpan.citation}
        </span>
      )}
    </div>
  ),
}));

import { ClaimsTab } from "@/components/report/claims-tab";

const VERIFIED_RECEIPT = {
  source_document_id: "US0000000001A1",
  source_name: "USPTO Patent Center",
  source_text_sha256: "a".repeat(64),
  source_retrieved_at: "2026-07-12T09:00:00.000Z",
  source_artifact_locator: `https://search.patentsview.org/api/v1/patent/?patent_id=US0000000001A1#sha256=${"a".repeat(64)}`,
  collector_identity: "runtime.uspto_claims",
  collector_version: "2026.07",
  provenance_cassette_sha256: "b".repeat(64),
};

// ---------------------------------------------------------------------------
// Test data builders
// ---------------------------------------------------------------------------

function makeElement(overrides: Partial<ClaimElement> = {}): ClaimElement {
  return {
    element_number: 1,
    element_text: "A compound of formula X",
    status: "met",
    reasoning: "Directly matches the structure",
    confidence: 0.9,
    evidence: "See specification page 12",
    ...overrides,
  };
}

function makeClaim(overrides: Partial<ClaimAnalysis> = {}): ClaimAnalysis {
  return {
    claim_number: 1,
    claim_type: "independent",
    depends_on: null,
    preamble: "A method for producing succinic acid comprising:",
    transitional_phrase: "comprising",
    elements: [
      makeElement({ element_number: 1, status: "met" }),
      makeElement({
        element_number: 2,
        status: "not_met",
        element_text: "a fermentation step",
      }),
      makeElement({
        element_number: 3,
        status: "partially_met",
        element_text: "purification",
      }),
    ],
    overall_status: "partially_met",
    overall_confidence: 0.75,
    reasoning: "Two of three elements are met or partially met.",
    ...overrides,
  };
}

function makePatentAnalysis(
  overrides: Partial<PatentAnalysis> = {},
): PatentAnalysis {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process for dicarboxylic acid production",
    assignee: "Fictional Meridian Therapeutics",
    expiry_date: "2038-01-15",
    claims_analyzed: [makeClaim()],
    risk_level: "high",
    risk_summary: "High risk due to process overlap",
    design_around_suggestions: [],
    orange_book_info: null,
    model_used: "claude-3-opus",
    thinking_text: "",
    input_tokens: 50000,
    output_tokens: 3000,
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
      cas_numbers: ["110-15-6"],
      molecular_formula: "C4H6O4",
      molecular_weight: 118.09,
      morgan_fp: "",
      maccs_keys: "",
      functional_groups: ["carboxylic_acid"],
      related_compounds: [],
      original_input: "succinic acid",
      input_type: "name",
    },
    risk_summary: {
      overall_risk: "medium",
      blocking_patents_count: 1,
      total_patents_analyzed: 2,
      key_risks: [],
      executive_summary: "",
      summary_validation_issues: [],
    },
    patent_analyses: [
      makePatentAnalysis(),
      makePatentAnalysis({
        patent_id: "US0000000002A1",
        title: "Purification method for organic acids",
        assignee: "Fictional Atlas Chemistry",
        risk_level: "medium",
        claims_analyzed: [
          makeClaim({
            claim_number: 1,
            claim_type: "independent",
            preamble: "A crystallization method",
            overall_status: "met",
            overall_confidence: 0.88,
            reasoning: "Both elements are fully met.",
            elements: [
              makeElement({ element_number: 1, status: "met" }),
              makeElement({ element_number: 2, status: "met" }),
            ],
          }),
          makeClaim({
            claim_number: 2,
            claim_type: "dependent",
            depends_on: 1,
            preamble: "",
            transitional_phrase: "wherein",
            overall_status: "not_met",
            overall_confidence: 0.92,
            reasoning: "Dependent limitation not met.",
            elements: [
              makeElement({
                element_number: 1,
                status: "not_met",
                element_text: "a temperature range of 50-80C",
              }),
            ],
          }),
        ],
      }),
    ],
    doe_assessments: [
      {
        patent_id: "US0000000001A1",
        claim_number: 1,
        element_number: 2,
        element_text: "a fermentation step",
        estoppel: {
          amendments_found: [],
          estoppel_applies: false,
          surrendered_scope: "",
          file_wrapper_available: true,
          rejections_found: [],
          prosecution_narrowing_count: 0,
        },
        fwr: {
          same_function: true,
          function_reasoning: "Same fermentation function",
          same_way: false,
          way_reasoning: "Different organism used",
          same_result: true,
          result_reasoning: "Same succinic acid output",
          equivalent: false,
          chemical_context: null,
        },
        overall_equivalent: false,
        confidence: 0.78,
        confidence_band: "MODERATE",
        reasoning: "Not equivalent — different organism pathway.",
      },
    ],
    invalidity_assessments: [],
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
    search_sources_used: ["pubchem"],
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
      patents_analyzed: 2,
    },
    patent_narratives: {},
    disclaimer: "",
    llm_models_used: {},
    total_input_tokens: 90000,
    total_output_tokens: 5500,
    estimated_cost_usd: 5.0,
    step_token_usage: [],
    ...overrides,
  };
}

describe("ClaimsTab", () => {
  it("does not expose reviewer-decision entry points without counsel capability", () => {
    const report = makeMockReport({
      claim_source_span_map: {
        generated_from: "test",
        entries: [
          {
            assertion_id: "scientist-hidden-review",
            patent_id: "US0000000001A1",
            claim_number: 1,
            element_number: 1,
            report_section: "claim_element_analysis",
            assertion_text: "Counsel review is required.",
            source_span_ids: [],
            support_status: "needs_review",
            customer_visible: true,
            review_required: true,
          },
        ],
        spans: {},
      },
    });

    render(
      <ClaimsTab
        analysisId="analysis-1"
        report={report}
        canReviewFindings={false}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Review claim/i }),
    ).not.toBeInTheDocument();
  });

  it("surfaces claim chart readiness from the source support ledger", () => {
    render(
      <ClaimsTab
        report={makeMockReport({
          claim_source_span_map: {
            generated_from: "test",
            entries: [
              {
                assertion_id: "assertion-1",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Element 1 is source supported.",
                source_span_ids: ["span-1"],
                support_status: "supported",
                customer_visible: true,
              },
              {
                assertion_id: "assertion-2",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 2,
                report_section: "claim_element_analysis",
                assertion_text: "Element 2 needs review.",
                source_span_ids: ["missing-span"],
                support_status: "needs_review",
                customer_visible: true,
              },
              {
                assertion_id: "assertion-3",
                patent_id: "US0000000002A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Unsupported assertion.",
                source_span_ids: ["span-3"],
                support_status: "unsupported",
                customer_visible: true,
              },
            ],
            spans: {
              "span-1": {
                ...VERIFIED_RECEIPT,
                span_id: "span-1",
                source_type: "verified_claim_text",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "US0000000001A1 claim 1",
                excerpt: "A source span supporting element 1.",
              },
              "span-3": {
                span_id: "span-3",
                source_type: "claim_reasoning",
                patent_id: "US0000000002A1",
                claim_number: 1,
                element_number: 1,
                citation: "US0000000002A1 claim 1",
                excerpt: "A cited but unsupported assertion.",
              },
            },
            needs_review_count: 1,
            unsupported_customer_visible_claim_count: 1,
          },
        })}
      />,
    );

    const readiness = screen.getByRole("region", {
      name: "Claim chart readiness",
    });
    expect(readiness).toHaveAttribute("data-testid", "claim-chart-readiness");
    expect(
      within(readiness).getByText(
        "Element mapping with source-support posture",
      ),
    ).toBeInTheDocument();
    expect(within(readiness).getByText("6 elements")).toBeInTheDocument();
    expect(within(readiness).getByText("1 supported")).toBeInTheDocument();
    expect(
      within(readiness).getByText("1 review / 1 unsupported"),
    ).toBeInTheDocument();
    expect(within(readiness).getByText("2 / 3 spans")).toBeInTheDocument();
    expect(
      within(readiness).getByText("1 missing source span"),
    ).toBeInTheDocument();
    expect(within(readiness).getByText("Unsupported")).toBeInTheDocument();
    expect(within(readiness).getByText("Needs review")).toBeInTheDocument();

    expect(
      screen.getByLabelText("US0000000001A1 claim support summary"),
    ).toHaveTextContent("Missing source spans");
    expect(
      screen.getByLabelText("US0000000002A1 claim support summary"),
    ).toHaveTextContent("Unsupported assertions");
    expect(screen.getByText("supported:assertion-1")).toBeInTheDocument();
    expect(
      screen.getByText("span-1:US0000000001A1 claim 1"),
    ).toBeInTheDocument();
    expect(screen.getByText("needs_review:assertion-2")).toBeInTheDocument();
    expect(screen.queryByText(/missing-span:/)).not.toBeInTheDocument();
  });

  it("renders patent IDs for all patent analyses", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("US0000000002A1").length).toBeGreaterThan(0);
  });

  it("keeps the full narrative collapsed until a reviewer requests it", () => {
    render(<ClaimsTab report={makeMockReport()} />);

    const toggle = screen.getByRole("button", { name: /Full claim narrative/ });
    const narrative = document.getElementById("full-claim-narrative");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(narrative).toHaveClass("hidden");
    expect(narrative).toHaveAttribute("data-print-redundant-narrative");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(narrative).not.toHaveClass("hidden");
  });

  it("selects the exact mapping assertion and verified span instead of the first tuple record", () => {
    render(
      <ClaimsTab
        report={makeMockReport({
          claim_source_span_map: {
            entries: [
              {
                assertion_id: "source-purpose",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_source",
                assertion_text: "Source purpose",
                source_span_ids: ["structural-first", "verified-second"],
                support_status: "supported",
                customer_visible: true,
              },
              {
                assertion_id: "mapping-purpose",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Mapping purpose",
                source_span_ids: ["reasoning-context"],
                support_status: "needs_review",
                customer_visible: true,
                review_required: true,
              },
            ],
            spans: {
              "structural-first": {
                span_id: "structural-first",
                source_type: "claim_text",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "Unverified structural span",
              },
              "verified-second": {
                ...VERIFIED_RECEIPT,
                span_id: "verified-second",
                source_type: "verified_claim_text",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "Verified exact claim span",
                excerpt: "A compound of formula X",
              },
              "reasoning-context": {
                span_id: "reasoning-context",
                source_type: "claim_reasoning",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "Reasoning context",
              },
            },
          },
        })}
      />,
    );

    expect(
      screen.getByText("needs_review:mapping-purpose"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("verified-second:Verified exact claim span"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/structural-first:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/reasoning-context:/)).not.toBeInTheDocument();
  });

  it("does not promote verified-type spans from unresolved assertions into the narrative", () => {
    render(
      <ClaimsTab
        report={makeMockReport({
          claim_source_span_map: {
            entries: [
              {
                assertion_id: "unresolved-mapping",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Unresolved mapping",
                source_span_ids: ["unresolved-verified-type"],
                support_status: "needs_review",
                customer_visible: true,
                review_required: true,
              },
            ],
            spans: {
              "unresolved-verified-type": {
                span_id: "unresolved-verified-type",
                source_type: "verified_claim_text",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "Must not be promoted",
              },
            },
          },
        })}
      />,
    );

    expect(
      screen.queryByText("unresolved-verified-type:Must not be promoted"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("needs_review:unresolved-mapping"),
    ).toBeInTheDocument();
  });

  it("does not mark missing claim span ledgers as healthy", () => {
    render(
      <ClaimsTab
        report={makeMockReport({ claim_source_span_map: undefined })}
      />,
    );

    const readiness = screen.getByRole("region", {
      name: "Claim chart readiness",
    });
    expect(
      within(readiness).getAllByText("Not reported").length,
    ).toBeGreaterThan(0);
    expect(
      within(readiness).getByText("No claim span ledger was reported"),
    ).toBeInTheDocument();
    expect(
      within(readiness).queryByText("Referenced spans are present"),
    ).not.toBeInTheDocument();
  });

  it("renders patent titles", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(
      screen.getAllByText(
        "Fermentation process for dicarboxylic acid production",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Purification method for organic acids").length,
    ).toBeGreaterThan(0);
  });

  it("does not pass hidden customer source support records to claim rows", () => {
    render(
      <ClaimsTab
        report={makeMockReport({
          claim_source_span_map: {
            generated_from: "test",
            entries: [
              {
                assertion_id: "hidden-assertion",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                report_section: "claim_element_analysis",
                assertion_text: "Internal-only support.",
                source_span_ids: ["hidden-span"],
                support_status: "supported",
                customer_visible: false,
              },
            ],
            spans: {
              "hidden-span": {
                span_id: "hidden-span",
                source_type: "element_evidence",
                patent_id: "US0000000001A1",
                claim_number: 1,
                element_number: 1,
                citation: "Hidden citation",
                excerpt: "Internal support excerpt.",
              },
            },
          },
        })}
      />,
    );

    expect(screen.queryByText(/hidden-assertion/)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden-span/)).not.toBeInTheDocument();
    expect(screen.getAllByText("US0000000001A1").length).toBeGreaterThan(0);
  });

  it("renders claim numbers for each patent", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    // US0000000001A1 has claim 1, US0000000002A1 has claims 1 and 2
    const claim1s = screen.getAllByText("Claim 1");
    expect(claim1s).toHaveLength(2);
    expect(screen.getByText("Claim 2")).toBeInTheDocument();
  });

  it("renders claim type badges", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    const independentBadges = screen.getAllByText("independent");
    expect(independentBadges).toHaveLength(2);
    expect(screen.getByText("dependent")).toBeInTheDocument();
  });

  it("renders overall status labels with correct display text", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(screen.getAllByText("Claim 1: Partial").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Claim 1: partially_met"),
    ).not.toBeInTheDocument();
    // Claim with overall_status "partially_met" -> "Partial"
    const partials = screen.getAllByText("Partial");
    expect(partials.length).toBeGreaterThanOrEqual(1);
    // "met" -> "Met"
    const mets = screen.getAllByText("Met");
    expect(mets.length).toBeGreaterThanOrEqual(1);
    // "not_met" -> "Not Met"
    const notMets = screen.getAllByText("Not Met");
    expect(notMets.length).toBeGreaterThanOrEqual(1);
  });

  it("renders transitional phrase badges", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    const comprisingBadges = screen.getAllByText("comprising");
    expect(comprisingBadges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("wherein")).toBeInTheDocument();
  });

  it("renders preamble text", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(
      screen.getByText(/A method for producing succinic acid comprising:/),
    ).toBeInTheDocument();
    expect(screen.getByText(/A crystallization method/)).toBeInTheDocument();
  });

  it("renders reasoning text in bordered container", () => {
    const { container } = render(<ClaimsTab report={makeMockReport()} />);
    expect(
      screen.getByText("Two of three elements are met or partially met."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Both elements are fully met."),
    ).toBeInTheDocument();
    // Reasoning blocks use border-l-2 class
    const reasoningBlocks = container.querySelectorAll(".border-l-2");
    expect(reasoningBlocks.length).toBeGreaterThanOrEqual(2);
  });

  it("renders claim elements via ClaimElementRow mock", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    // US0000000001A1 has 3 elements, US0000000002A1 claim 1 has 2, claim 2 has 1 = 6 total
    const elements = screen.getAllByTestId(/^claim-element-/);
    expect(elements).toHaveLength(6);
  });

  it("passes report citation metadata into claim element rows", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(screen.getAllByText("rpt-001:0.9.0")).toHaveLength(6);
  });

  it("attaches DoE assessment only to not_met or partially_met elements", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    // Only element 2 of US0000000001A1 claim 1 should have DoE (it's "not_met")
    expect(screen.getByTestId("doe-attached-2")).toBeInTheDocument();
    // Element 1 is "met" — should NOT get DoE even though there's a DoE assessment for the patent
    expect(screen.queryByTestId("doe-attached-1")).not.toBeInTheDocument();
  });

  it("shows empty state when no patent analyses exist", () => {
    const report = makeMockReport({ patent_analyses: [] });
    render(<ClaimsTab report={report} />);
    expect(
      screen.getByText("No claim analyses available."),
    ).toBeInTheDocument();
  });

  it("does not show empty state when patent analyses exist", () => {
    render(<ClaimsTab report={makeMockReport()} />);
    expect(
      screen.queryByText("No claim analyses available."),
    ).not.toBeInTheDocument();
  });

  it("truncates long preambles at 200 characters", () => {
    const longPreamble = "A".repeat(250);
    const report = makeMockReport({
      patent_analyses: [
        makePatentAnalysis({
          claims_analyzed: [makeClaim({ preamble: longPreamble })],
        }),
      ],
    });
    render(<ClaimsTab report={report} />);
    expect(
      screen.getByText(longPreamble.slice(0, 200) + "..."),
    ).toBeInTheDocument();
  });
});
