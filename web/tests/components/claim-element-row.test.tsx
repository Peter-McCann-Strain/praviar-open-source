import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type {
  ClaimAssertionSupport,
  ClaimElement,
  PatentHit,
  SourceSpanReference,
} from "@praviar/shared-types";

import { ClaimElementRow } from "@/components/patent/claim-element-row";

function makeElement(overrides: Partial<ClaimElement> = {}): ClaimElement {
  return {
    element_number: 1,
    element_text:
      "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
    status: "met",
    reasoning:
      "The proposed process uses recombinant E. coli to produce succinic acid.",
    confidence: 0.95,
    evidence:
      "Succinic acid is a C4 dicarboxylic acid and E. coli is a prokaryotic organism.",
    ...overrides,
  };
}

function makePatent(overrides: Partial<PatentHit> = {}): PatentHit {
  return {
    patent_id: "US0000000001A1",
    title:
      "Methods for producing C4 dicarboxylic acids using engineered prokaryotic microorganisms",
    abstract: "A fermentation process for producing C4 dicarboxylic acids.",
    claims_text:
      "1. A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism.",
    sources: ["demo_fixture"],
    confidence_score: 0.94,
    filing_date: "2015-06-14",
    priority_date: "2014-06-14",
    expiry_date: "2035-06-14",
    assignees: ["Fictional Meridian Therapeutics"],
    inventors: ["M. Carter"],
    cpc_codes: ["C12P 7/46"],
    legal_status: "active",
    match_type: "claim_analysis",
    tanimoto_score: 0.82,
    is_granted: true,
    legal_events: [],
    family: null,
    patent_term_info: null,
    ...overrides,
  };
}

function makeSourceSupport(
  overrides: Partial<ClaimAssertionSupport> = {},
): ClaimAssertionSupport {
  return {
    assertion_id: "assertion-1",
    patent_id: "US0000000001A1",
    claim_number: 1,
    element_number: 1,
    report_section: "claim_element_analysis",
    assertion_text: "Element 1 is supported.",
    source_span_ids: ["span-1"],
    support_status: "supported",
    customer_visible: true,
    ...overrides,
  };
}

function makeSourceSpan(
  overrides: Partial<SourceSpanReference> = {},
): SourceSpanReference {
  return {
    span_id: "span-1",
    source_type: "element_evidence",
    patent_id: "US0000000001A1",
    claim_number: 1,
    element_number: 1,
    citation: "US0000000001A1 claim 1",
    excerpt:
      "Succinic acid is a C4 dicarboxylic acid and E. coli is prokaryotic.",
    ...overrides,
  };
}

describe("ClaimElementRow", () => {
  it("surfaces readable claim text and evidence before expansion", () => {
    const element = makeElement();

    render(
      <ClaimElementRow
        element={element}
        patent={makePatent()}
        claimNumber={1}
      />,
    );

    const row = screen.getByTestId("claim-element-row-1");
    expect(within(row).getByTestId("claim-element-text-1")).toHaveTextContent(
      element.element_text,
    );
    expect(
      within(row).getByTestId("claim-element-evidence-summary-1"),
    ).toHaveTextContent("Evidence excerpt");
    expect(
      within(row).getByTestId("claim-element-evidence-summary-1"),
    ).toHaveTextContent("C4 dicarboxylic acid");
    expect(
      within(row).getByRole("button", {
        name: /view source for US0000000001A1 claim 1 element 1/i,
      }),
    ).toBeInTheDocument();
    const disclosure = within(row).getByRole("button", {
      name: /toggle details for US0000000001A1 claim 1 element 1/i,
    });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(disclosure).toHaveAttribute(
      "aria-controls",
      "us0000000001a1-claim-1-element-1-details",
    );
    expect(
      document.getElementById("us0000000001a1-claim-1-element-1"),
    ).toBeInTheDocument();
    expect(
      document.getElementById("us0000000001a1-claim-1-element-1-details"),
    ).toBeInTheDocument();
    expect(within(row).getByText("Support")).toBeInTheDocument();
    expect(within(row).getByText("Evidence span")).toBeInTheDocument();
    expect(within(row).getByText("Quoted")).toBeInTheDocument();
    expect(within(row).getByText("Source record")).toBeInTheDocument();
    expect(within(row).getByText("US0000000001A1")).toHaveAttribute(
      "title",
      "US0000000001A1",
    );
  });

  it("makes missing evidence spans visible before expansion", () => {
    const element = makeElement({ evidence: "" });

    render(
      <ClaimElementRow
        element={element}
        patent={makePatent()}
        claimNumber={1}
      />,
    );

    const row = screen.getByTestId("claim-element-row-1");
    expect(within(row).getByText("Missing quote")).toHaveClass("text-warning");
    expect(
      within(row).queryByTestId("claim-element-evidence-summary-1"),
    ).not.toBeInTheDocument();
  });

  it("surfaces governed ledger status and real source span before expansion", () => {
    render(
      <ClaimElementRow
        element={makeElement()}
        patent={makePatent()}
        claimNumber={1}
        sourceSupport={makeSourceSupport({ support_status: "needs_review" })}
        sourceSpan={makeSourceSpan()}
      />,
    );

    const row = screen.getByTestId("claim-element-row-1");
    expect(within(row).getByText("Needs Review")).toBeInTheDocument();
    expect(within(row).getByText("Ledger span")).toBeInTheDocument();
    expect(within(row).getByText("US0000000001A1 claim 1")).toHaveAttribute(
      "title",
      "US0000000001A1 claim 1",
    );
  });

  it("keeps source traceability when patent details are absent but ledger spans exist", () => {
    render(
      <ClaimElementRow
        element={makeElement()}
        patent={null}
        patentId="US0000000001A1"
        claimNumber={1}
        sourceSupport={makeSourceSupport()}
        sourceSpan={makeSourceSpan()}
      />,
    );

    const row = screen.getByTestId("claim-element-row-1");
    const sourceButton = within(row).getByRole("button", {
      name: /view source for US0000000001A1 claim 1 element 1/i,
    });
    expect(sourceButton).toBeInTheDocument();

    fireEvent.click(sourceButton);

    expect(screen.getByTestId("evidence-drilldown")).toBeVisible();
    expect(screen.getByText("Ledger source span")).toBeInTheDocument();
    expect(
      screen.getAllByText(/US0000000001A1 claim 1/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByTestId("evidence-drilldown-highlight"),
    ).toHaveTextContent("Succinic acid is a C4 dicarboxylic acid");
  });

  it("uses unique disclosure ids when patents share claim and element numbers", () => {
    render(
      <>
        <ClaimElementRow
          element={makeElement()}
          patent={makePatent({ patent_id: "US0000000001A1" })}
          claimNumber={1}
        />
        <ClaimElementRow
          element={makeElement()}
          patent={makePatent({ patent_id: "US0000000002A1" })}
          claimNumber={1}
        />
      </>,
    );

    const disclosures = screen.getAllByRole("button", {
      name: /toggle details for/i,
    });
    const ids = disclosures.map((button) =>
      button.getAttribute("aria-controls"),
    );
    expect(new Set(ids).size).toBe(ids.length);
    ids.forEach((id) => {
      expect(id).toBeTruthy();
      expect(document.getElementById(id ?? "")).toBeInTheDocument();
      expect(
        document.getElementById(String(id).replace(/-details$/, "")),
      ).toBeInTheDocument();
    });
  });

  it("opens the evidence drilldown from the source button", () => {
    const element = makeElement();

    render(
      <ClaimElementRow
        element={element}
        patent={makePatent()}
        claimNumber={1}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /view source for US0000000001A1 claim 1 element 1/i,
      }),
    );

    expect(screen.getByTestId("evidence-drilldown")).toBeVisible();
    expect(screen.getByText("Element Under Analysis")).toBeInTheDocument();
    expect(screen.getByText("Analyst Evidence")).toBeInTheDocument();
    expect(
      screen.getByTestId("evidence-drilldown-highlight"),
    ).toHaveTextContent("A method for producing a C4 dicarboxylic acid");
  });
});
