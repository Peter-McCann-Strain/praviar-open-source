import { describe, expect, it } from "vitest";

import {
  SHOWCASE_FIXTURE_RECEIPT,
  SHOWCASE_PAYLOAD,
  SHOWCASE_REPORT,
} from "@/lib/showcase-report";
import { buildCitationMap, parseCitationMarkers } from "@/types/citation";

describe("canonical showcase report", () => {
  it("projects the canonical fictional fixture with its receipt", () => {
    expect(SHOWCASE_REPORT.compound.name).toBe(
      SHOWCASE_PAYLOAD.compound.display_name,
    );
    expect(SHOWCASE_REPORT.routing_profile).toEqual({
      showcase_fixture: SHOWCASE_FIXTURE_RECEIPT,
    });
    expect(SHOWCASE_REPORT.claim_source_span_map.generated_from).toBe(
      SHOWCASE_FIXTURE_RECEIPT.fixtureId,
    );
    expect(SHOWCASE_REPORT.patent_analyses).toHaveLength(
      SHOWCASE_PAYLOAD.analysis.families.length,
    );
  });

  it("keeps the showcase zero-spend, structure-free and review gated", () => {
    expect(SHOWCASE_REPORT.compound.canonical_smiles).toBe("");
    expect(SHOWCASE_REPORT.total_input_tokens).toBe(0);
    expect(SHOWCASE_REPORT.total_output_tokens).toBe(0);
    expect(SHOWCASE_REPORT.estimated_cost_usd).toBe(0);
    expect(SHOWCASE_REPORT.clearance_decision?.decision).toBe("unclear");
    expect(
      SHOWCASE_REPORT.claim_source_span_map.needs_review_count,
    ).toBeGreaterThan(0);
    expect(SHOWCASE_REPORT.disclaimer).toMatch(/fictional/i);
  });

  it("adds a summary marker only for the real first canonical source span", () => {
    const { indices } = parseCitationMarkers(
      SHOWCASE_REPORT.risk_summary.executive_summary,
    );
    const citations = buildCitationMap(
      SHOWCASE_REPORT.patent_analyses,
      SHOWCASE_REPORT.claim_source_span_map,
    );

    expect(indices).toEqual([1]);
    expect(citations.get(1)).toMatchObject({
      patentId: SHOWCASE_PAYLOAD.analysis.families[0].publications[0],
      text: SHOWCASE_PAYLOAD.analysis.families[0].claims[0].text,
    });
    expect(citations.get(1)?.section).toContain(
      SHOWCASE_PAYLOAD.analysis.evidence[0].source_reference,
    );
  });

  it("contains no legacy product fixture identities", () => {
    const serialized = JSON.stringify(SHOWCASE_REPORT);

    expect(serialized).not.toMatch(
      /aspirin|acetylsalicylic|sofosbuvir|succinic acid|US6977252|50-78-2/i,
    );
  });
});
