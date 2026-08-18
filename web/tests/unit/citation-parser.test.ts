import { describe, it, expect } from "vitest";
import { parseCitationMarkers, buildCitationMap } from "@/types/citation";

describe("parseCitationMarkers", () => {
  it("returns plain text when no markers present", () => {
    const result = parseCitationMarkers("No citations here.");
    expect(result.segments).toEqual([
      { type: "text", content: "No citations here." },
    ]);
    expect(result.indices).toEqual([]);
  });

  it("parses a single citation marker", () => {
    const result = parseCitationMarkers("This is relevant [1] to the case.");
    expect(result.segments).toEqual([
      { type: "text", content: "This is relevant " },
      { type: "citation", index: 1 },
      { type: "text", content: " to the case." },
    ]);
    expect(result.indices).toEqual([1]);
  });

  it("parses multiple citation markers", () => {
    const result = parseCitationMarkers("Claims [1] and [2] overlap with [3].");
    expect(result.segments).toHaveLength(7);
    expect(result.indices).toEqual([1, 2, 3]);
  });

  it("handles adjacent markers", () => {
    const result = parseCitationMarkers("See [1][2] for details.");
    expect(result.segments).toEqual([
      { type: "text", content: "See " },
      { type: "citation", index: 1 },
      { type: "citation", index: 2 },
      { type: "text", content: " for details." },
    ]);
    expect(result.indices).toEqual([1, 2]);
  });

  it("handles marker at start", () => {
    const result = parseCitationMarkers("[1] is the first patent.");
    expect(result.segments[0]).toEqual({ type: "citation", index: 1 });
  });

  it("handles marker at end", () => {
    const result = parseCitationMarkers("See the patent [5]");
    const last = result.segments[result.segments.length - 1];
    expect(last).toEqual({ type: "citation", index: 5 });
  });

  it("deduplicates indices", () => {
    const result = parseCitationMarkers("Patent [1] is mentioned again [1].");
    expect(result.indices).toEqual([1]);
  });

  it("handles multi-digit numbers", () => {
    const result = parseCitationMarkers("Reference [12] and [123].");
    expect(result.indices).toEqual([12, 123]);
  });

  it("handles empty string", () => {
    const result = parseCitationMarkers("");
    expect(result.segments).toEqual([{ type: "text", content: "" }]);
    expect(result.indices).toEqual([]);
  });
});

describe("buildCitationMap", () => {
  it("creates a 1-based map from patent analyses", () => {
    const map = buildCitationMap([
      { patent_id: "US123", title: "First Patent", claims_analyzed: [] },
      { patent_id: "US456", title: "Second Patent", claims_analyzed: [] },
    ]);
    expect(map.size).toBe(2);
    expect(map.get(1)?.patentId).toBe("US123");
    expect(map.get(2)?.patentId).toBe("US456");
    expect(map.get(1)?.section).toBe("patent:US123");
  });

  it("uses customer-visible claim source spans when available", () => {
    const map = buildCitationMap(
      [
        {
          patent_id: "US123",
          title: "First Patent",
          claims_analyzed: [{ claim_number: 4 }],
        },
      ],
      {
        entries: [
          {
            assertion_id: "unsupported",
            assertion_text: "Unsupported assertion should not be used.",
            customer_visible: true,
            patent_id: "US123",
            source_span_ids: ["span-unsupported"],
            support_status: "unsupported",
          },
          {
            assertion_id: "supported",
            assertion_text: "Claim element support assertion.",
            claim_number: 1,
            customer_visible: true,
            element_number: 2,
            patent_id: "US123",
            source_span_ids: ["span-supported"],
            support_status: "supported",
          },
        ],
        spans: {
          "span-supported": {
            span_id: "span-supported",
            source_type: "element_evidence",
            patent_id: "US123",
            claim_number: 1,
            element_number: 2,
            citation: "US123 claim 1",
            excerpt: "Claim 1 recites a recombinant production method.",
          },
          "span-unsupported": {
            span_id: "span-unsupported",
            source_type: "claim_text",
            patent_id: "US123",
            excerpt: "This should not surface as supporting evidence.",
          },
        },
      },
    );

    expect(map.get(1)).toEqual(
      expect.objectContaining({
        claimNumber: 1,
        patentId: "US123",
        section: "US123 claim 1 · Element evidence · Claim 1 · Element 2",
        text: "Claim 1 recites a recombinant production method.",
      }),
    );
  });

  it("labels verified claim text provenance distinctly", () => {
    const map = buildCitationMap(
      [{ patent_id: "EP123", title: "Verified patent" }],
      {
        entries: [
          {
            assertion_id: "verified",
            customer_visible: true,
            patent_id: "EP123",
            source_span_ids: ["span-verified"],
            support_status: "supported",
          },
        ],
        spans: {
          "span-verified": {
            span_id: "span-verified",
            source_type: "verified_claim_text",
            patent_id: "EP123",
            claim_number: 7,
            citation: "EP123 claim 7",
            excerpt: "Claim 7 recites the verified composition.",
          },
        },
      },
    );

    expect(map.get(1)?.section).toBe(
      "EP123 claim 7 · Verified claim text · Claim 7",
    );
  });

  it("handles empty array", () => {
    const map = buildCitationMap([]);
    expect(map.size).toBe(0);
  });
});
