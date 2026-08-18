import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ClaimDecisionMatrix } from "@/components/report/claim-decision-matrix";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { FTOReport } from "@praviar/shared-types";

const REPORT = {
  report_id: "report-queue",
  generated_at: "2026-07-12T12:00:00.000Z",
  praviar_pipeline_version: "1.0.0",
  patent_analyses: [
    {
      patent_id: "US123B2",
      jurisdiction: "US",
      title: "Exact member",
      risk_level: "high",
      risk_summary: "Test",
      expiry_date: "2034-02-01",
      claims_analyzed: [
        {
          claim_number: 1,
          claim_type: "independent",
          overall_status: "met",
          reasoning: "Test",
          elements: [
            {
              element_number: 1,
              element_text: "a compound limitation",
              status: "met",
              reasoning: "The product structure maps to the limitation.",
              evidence: "Product structure record PRV-1.",
            },
          ],
        },
      ],
    },
  ],
  patent_details: {
    US123B2: {
      patent_id: "US123B2",
      title: "Exact member",
      legal_status: "active",
      jurisdiction: "US",
      family_id: "fam-1",
    },
  },
  claim_source_span_map: {
    entries: [
      {
        assertion_id: "source-1",
        patent_id: "US123B2",
        claim_number: 1,
        element_number: 1,
        report_section: "verified_claim_text",
        assertion_text: "Verified claim text",
        source_span_ids: ["verified-1"],
        support_status: "supported",
        customer_visible: true,
        review_required: false,
      },
      {
        assertion_id: "mapping-1",
        patent_id: "US123B2",
        claim_number: 1,
        element_number: 1,
        report_section: "claim_element_analysis",
        assertion_text: "AI mapping",
        source_span_ids: [],
        support_status: "needs_review",
        customer_visible: true,
        review_required: true,
      },
    ],
    spans: {
      "verified-1": {
        span_id: "verified-1",
        source_type: "verified_claim_text",
        patent_id: "US123B2",
        claim_number: 1,
        element_number: 1,
        citation: "US123B2 claim 1",
        excerpt: "a compound limitation",
        source_document_id: "US123B2",
        source_name: "USPTO Patent Center",
        source_text_sha256: "a".repeat(64),
        source_retrieved_at: "2026-07-12T09:00:00.000Z",
        source_artifact_locator: `https://search.patentsview.org/api/v1/patent/?patent_id=US123B2#sha256=${"a".repeat(64)}`,
        collector_identity: "runtime.uspto_claims",
        collector_version: "2026.07",
        provenance_cassette_sha256: "b".repeat(64),
      },
    },
  },
} as unknown as FTOReport;

const DECISIONS: ReviewerDecisionListResponse = {
  items: [],
  counts: { accept: 0, reject: 0, edit: 0 },
};

const CLEAN_REPORT = {
  ...REPORT,
  claim_source_span_map: {
    ...REPORT.claim_source_span_map,
    entries: REPORT.claim_source_span_map.entries.map((entry) =>
      entry.assertion_id === "mapping-1"
        ? {
            ...entry,
            support_status: "supported",
            review_required: false,
          }
        : entry,
    ),
  },
} as unknown as FTOReport;

describe("ClaimDecisionMatrix", () => {
  it("separates AI analysis, complete claim provenance, and human review", () => {
    const onReviewFinding = vi.fn();
    render(
      <ClaimDecisionMatrix
        onReviewFinding={onReviewFinding}
        report={REPORT}
        reviewerDecisions={DECISIONS}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Family × claim source-review matrix",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Authority wording only. This does not establish product mapping/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Synthetic research preview; not a legal clearance opinion.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "1 · Source fact" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "2 · AI-assisted inference" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "3 · Human decision" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Met")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Feature evidence map for claim 1 element 1"),
    ).toBeInTheDocument();
    expect(screen.getByText("Authority text captured")).toBeInTheDocument();
    expect(screen.getByText("Product evidence cited")).toBeInTheDocument();
    expect(screen.getAllByText("Mapping needs review").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Review pending").length).toBeGreaterThan(1);
    expect(
      screen.getByText("1 complete provenance receipt"),
    ).toBeInTheDocument();
    expect(screen.getByText("USPTO Patent Center")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open exact source" }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("search.patentsview.org"),
    );
    expect(
      screen.getByText("Product structure record PRV-1."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Status provenance and expiry basis are not included/),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Review claim 1 element 1 for US123B2",
      }),
    );
    expect(onReviewFinding).toHaveBeenCalledWith("mapping-1");
  });

  it("keeps source, AI, and human layers in review order on narrow layouts", () => {
    render(
      <ClaimDecisionMatrix report={REPORT} reviewerDecisions={DECISIONS} />,
    );

    const row = screen.getByTestId(
      "claim-decision-row-US123B2:claim-1:element-1",
    );
    const source = within(row).getByRole("heading", {
      name: "1 · Source fact",
    });
    const inference = within(row).getByRole("heading", {
      name: "2 · AI-assisted inference",
    });
    const decision = within(row).getByRole("heading", {
      name: "3 · Human decision",
    });

    expect(
      source.compareDocumentPosition(inference) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      inference.compareDocumentPosition(decision) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(row).getByRole("link", { name: "Open exact source" }),
    ).toBeVisible();
    expect(
      screen.getByText(/Mobile focus mode shows one exact element at a time/),
    ).toBeInTheDocument();
    expect(row).toHaveAttribute(
      "data-claim-coordinate",
      "US123B2:claim-1:element-1",
    );
    expect(
      row.querySelector("[data-print-claim-coordinate-header]"),
    ).toHaveTextContent("US123B2 · Claim 1 · Element 1");
  });

  it("renders intentionally unavailable counsel decisions as unavailable, not pending", () => {
    render(
      <ClaimDecisionMatrix
        report={REPORT}
        decisionsUnavailable
        reviewerDecisions={DECISIONS}
      />,
    );

    expect(
      screen.getAllByText("Decision ledger unavailable").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Review pending")).not.toBeInTheDocument();
    expect(screen.queryByText(/Accepted ·/)).not.toBeInTheDocument();
  });

  it("filters completed views without removing the exact record", () => {
    render(
      <ClaimDecisionMatrix report={REPORT} reviewerDecisions={DECISIONS} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Not met" }));
    expect(
      screen.getByText("No elements match this filter"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All elements" }));
    expect(screen.getAllByText("a compound limitation").length).toBeGreaterThan(
      0,
    );
  });

  it("defaults to the complete record when no element needs action", () => {
    render(
      <ClaimDecisionMatrix
        report={CLEAN_REPORT}
        reviewerDecisions={DECISIONS}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Needs action (0)" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "All elements" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByTestId("claim-decision-row-US123B2:claim-1:element-1"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No elements match this filter"),
    ).not.toBeInTheDocument();
  });

  it("opens and focuses the exact claim selected by a blocker deep-link", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    render(
      <ClaimDecisionMatrix
        focusedClaimNumber={1}
        focusedPatentId="US123B2"
        report={REPORT}
        reviewerDecisions={DECISIONS}
      />,
    );

    const row = screen.getByTestId(
      "claim-decision-row-US123B2:claim-1:element-1",
    );
    await waitFor(() => expect(row).toHaveFocus());
    expect(row).toHaveAttribute("data-patent-id", "US123B2");
    expect(row).toHaveAttribute("data-claim-number", "1");
    expect(row.querySelector("details")).toHaveAttribute("open");
    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "center",
    });
  });

  it("clears a stale needs-action filter when the queue becomes clean", async () => {
    const { rerender } = render(
      <ClaimDecisionMatrix report={REPORT} reviewerDecisions={DECISIONS} />,
    );

    expect(
      screen.getByRole("button", { name: "Needs action (1)" }),
    ).toHaveAttribute("aria-pressed", "true");

    rerender(
      <ClaimDecisionMatrix
        report={CLEAN_REPORT}
        reviewerDecisions={DECISIONS}
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "All elements" }),
      ).toHaveAttribute("aria-pressed", "true"),
    );
    expect(
      screen.getByRole("button", { name: "Needs action (0)" }),
    ).toBeDisabled();
  });
});
