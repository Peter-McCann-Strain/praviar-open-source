import { describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ClaimElement, PatentHit } from "@praviar/shared-types";

import {
  EvidenceDrilldown,
  findMatchedSpan,
} from "@/components/report/evidence-drilldown";

function makePatent(overrides: Partial<PatentHit> = {}): PatentHit {
  return {
    patent_id: "US0000000001A1",
    title: "Fermentation process for succinic acid",
    abstract: "An improved fermentation process.",
    claims_text:
      "1. A process for producing succinic acid wherein the compound has purity >= 99% and is obtained via aerobic fermentation.",
    sources: [],
    confidence_score: 0.8,
    filing_date: "2018-01-10",
    priority_date: "2017-01-10",
    expiry_date: "2038-01-15",
    assignees: ["Fictional Meridian Therapeutics"],
    inventors: ["Jane Doe"],
    cpc_codes: ["C12P 7/46"],
    legal_status: "active",
    match_type: "similarity",
    tanimoto_score: 0.7,
    is_granted: true,
    legal_events: [],
    family: null,
    patent_term_info: null,
    ...overrides,
  };
}

function makeElement(overrides: Partial<ClaimElement> = {}): ClaimElement {
  return {
    element_number: 2,
    element_text: "wherein the compound has purity >= 99%",
    status: "met",
    reasoning: "The claim language directly recites the purity threshold.",
    confidence: 0.91,
    evidence: "wherein the compound has purity >= 99%",
    ...overrides,
  };
}

describe("findMatchedSpan", () => {
  it("locates evidence quote exactly inside claim text", () => {
    const patent = makePatent();
    const element = makeElement();
    const span = findMatchedSpan(patent.claims_text, element);
    expect(span.source).toBe("evidence");
    expect(patent.claims_text.slice(span.start, span.end)).toBe(
      element.evidence,
    );
  });

  it("falls back to element_text when evidence is empty", () => {
    const patent = makePatent();
    const element = makeElement({ evidence: "" });
    const span = findMatchedSpan(patent.claims_text, element);
    expect(span.source).toBe("element_text");
    expect(patent.claims_text.slice(span.start, span.end)).toBe(
      element.element_text,
    );
  });

  it("matches despite whitespace differences", () => {
    const patent = makePatent({
      claims_text:
        "1. A process wherein  the  compound   has\tpurity >=   99% obtained by fermentation.",
    });
    const element = makeElement({
      evidence: "wherein the compound has purity >= 99%",
    });
    const span = findMatchedSpan(patent.claims_text, element);
    expect(span.source).toBe("evidence");
    // The matched slice should begin with "wherein" and end near the percent sign.
    const matched = patent.claims_text.slice(span.start, span.end);
    expect(matched.toLowerCase()).toContain("wherein");
    expect(matched).toContain("99%");
  });

  it("returns a none result when no match exists", () => {
    const patent = makePatent({ claims_text: "Completely different text." });
    const element = makeElement({
      evidence: "wherein the compound has purity >= 99%",
      element_text: "wherein the compound has purity >= 99%",
    });
    const span = findMatchedSpan(patent.claims_text, element);
    expect(span.source).toBe("none");
    expect(span.start).toBe(-1);
  });
});

describe("EvidenceDrilldown", () => {
  it("renders nothing when patent is missing", () => {
    const { container } = render(
      <EvidenceDrilldown
        patent={null}
        claimNumber={1}
        element={makeElement()}
        open
        onClose={() => {}}
      />,
    );
    expect(container.textContent).toBe("");
  });

  it("highlights the matched evidence span in the claim text", () => {
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement()}
        reportCitation={{
          reportId: "rpt-001",
          generatedAt: "2026-03-12T10:00:00Z",
          pipelineVersion: "0.9.0",
        }}
        open
        onClose={() => {}}
      />,
    );
    const mark = screen.getByTestId("evidence-drilldown-highlight");
    expect(mark.textContent).toBe("wherein the compound has purity >= 99%");
    // Header shows patent id and claim/element position
    expect(screen.getAllByText(/US0000000001A1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Claim 1, Element 2/)).toBeTruthy();
    expect(screen.getByText("Report record")).toBeInTheDocument();
    expect(screen.getByText("rpt-001")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /USPTO Patent Public Search/i }),
    ).toHaveAttribute("href", "https://ppubs.uspto.gov/pubwebapp/");
    expect(
      screen.queryByRole("link", { name: /^USPTO$/i }),
    ).not.toBeInTheDocument();
  });

  it("shows a graceful fallback when no passage is located", () => {
    render(
      <EvidenceDrilldown
        patent={makePatent({ claims_text: "Entirely unrelated text." })}
        claimNumber={1}
        element={makeElement()}
        open
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("evidence-drilldown-no-match")).toBeTruthy();
    expect(screen.queryByTestId("evidence-drilldown-highlight")).toBeNull();
  });

  it("renders partially met evidence as a caution state", () => {
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement({ status: "partially_met" })}
        open
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Partially Met")).toHaveClass(
      "border-warning/25",
      "bg-warning/10",
      "text-warning",
    );
  });

  it("renders met evidence as a risk state", () => {
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement({ status: "met" })}
        open
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Met")).toHaveClass(
      "border-error/25",
      "bg-error/10",
      "text-error",
    );
  });

  it("renders not met evidence as a lower-risk state", () => {
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement({ status: "not_met" })}
        open
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Not Met")).toHaveClass(
      "border-success/25",
      "bg-success/10",
      "text-success",
    );
  });

  it("copies an audit-grade evidence citation packet", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    const onClose = vi.fn();
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement()}
        reportCitation={{
          reportId: "rpt-001",
          generatedAt: "2026-03-12T10:00:00Z",
          pipelineVersion: "0.9.0",
          reportFingerprint: "sha256:report-fingerprint",
          reviewerDecision: "accepted",
          reviewerTimestamp: "2026-03-12T11:15:00Z",
        }}
        open
        onClose={onClose}
      />,
    );

    const copyBtn = screen.getByTestId("evidence-drilldown-copy");
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(writeText).toHaveBeenCalledTimes(1);
    const packet = writeText.mock.calls[0][0];
    expect(packet).toContain("Praviar evidence citation packet");
    expect(packet).toContain("Report: rpt-001");
    expect(packet).toContain("Generated: 2026-03-12T10:00:00Z");
    expect(packet).toContain("Pipeline: 0.9.0");
    expect(packet).toContain("Report fingerprint: sha256:report-fingerprint");
    expect(packet).toContain(
      "Reviewer decision: accepted at 2026-03-12T11:15:00Z",
    );
    expect(packet).toContain("Patent: US0000000001A1");
    expect(packet).toContain("Claim element: Claim 1, element 2");
    expect(packet).toContain("Match posture: Analyst quote matched");
    expect(packet).toContain("Status: Met");
    expect(packet).toContain("Confidence: 91% confidence");
    expect(packet).toContain(
      "Source span ID: US0000000001A1:claim-1:element-2:offset-41-79",
    );
    expect(packet).toContain(
      "Google Patents: https://patents.google.com/patent/US0000000001A1",
    );
    await waitFor(() => {
      expect(screen.getByText("Copied")).toBeInTheDocument();
    });
  });

  it("copies governed source span metadata when ledger context is provided", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement()}
        sourceSupport={{
          assertion_id: "assertion-1",
          patent_id: "US0000000001A1",
          claim_number: 1,
          element_number: 2,
          report_section: "claim_element_analysis",
          assertion_text: "Element 2 is supported.",
          source_span_ids: ["span-real-1"],
          support_status: "supported",
          customer_visible: true,
        }}
        sourceSpan={{
          span_id: "span-real-1",
          source_type: "element_evidence",
          patent_id: "US0000000001A1",
          claim_number: 1,
          element_number: 2,
          citation: "US0000000001A1 claim 1",
          excerpt: "A governed source excerpt from the claim ledger.",
        }}
        open
        onClose={() => {}}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("evidence-drilldown-copy"));
    });

    const packet = writeText.mock.calls[0][0];
    expect(packet).toContain("Source span ID: span-real-1");
    expect(packet).toContain("Claim support status: Supported");
    expect(packet).toContain(
      "Ledger excerpt: A governed source excerpt from the claim ledger.",
    );
  });

  it("shows a clear state when clipboard copy is unavailable", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement()}
        open
        onClose={() => {}}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId("evidence-drilldown-copy"));
    });

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Copy unavailable")).toBeInTheDocument();
  });

  it("invokes onClose when the dialog close control is activated", () => {
    const onClose = vi.fn();
    render(
      <EvidenceDrilldown
        patent={makePatent()}
        claimNumber={1}
        element={makeElement()}
        open
        onClose={onClose}
      />,
    );
    // Radix Dialog renders a Close button with accessible name "Close".
    const closeBtn = screen.getAllByRole("button", { name: /close/i })[0];
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });
});
