import { describe, expect, it } from "vitest";
import {
  SHOWCASE_FIXTURE_RECEIPT,
  SHOWCASE_PAYLOAD,
} from "@/lib/showcase-report";
import { getMarketingDemoArtifact } from "@/marketing/live-demo";

describe("public marketing sample", () => {
  it("keeps fictional evidence visibly synthetic and removes plausible identifiers", () => {
    const sample = getMarketingDemoArtifact();
    const serialized = JSON.stringify(sample);

    expect(sample.sourceReference).toContain(
      `${SHOWCASE_FIXTURE_RECEIPT.fixtureId}@${SHOWCASE_FIXTURE_RECEIPT.fixtureVersion}`,
    );
    expect(sample.sourceReference).toContain(SHOWCASE_FIXTURE_RECEIPT.digest);
    expect(sample.claimSnapshot.patentId).toMatch(/^SYNTH-US-\d{3}$/);
    expect(sample.blockingPatentsCount).toBe(0);
    expect(sample.familiesFlaggedForReviewCount).toBe(
      SHOWCASE_PAYLOAD.analysis.families.filter(
        (family) =>
          family.posture !== "no_blocker_identified_in_searched_record",
      ).length,
    );
    expect(sample.familiesFlaggedForReviewCount).toBe(1);
    expect(sample.evidenceRows?.length).toBeGreaterThan(0);
    expect(
      sample.evidenceRows?.every((row) => row.patentId.startsWith("SYNTH-")),
    ).toBe(true);
    expect(serialized).not.toMatch(/US0000000001A1|US0000000002A1/);
    expect(serialized).not.toMatch(/Pfizer|BASF|Novozymes|DSM|Myriant|Gilead/i);
    expect(serialized).not.toMatch(/IPR\d{4}-\d+/i);
    expect(serialized).not.toMatch(
      /clear of infringement concerns|could go either way in litigation|high blocking potential/i,
    );
    expect(JSON.stringify(sample.dataLimitations)).not.toMatch(
      /PatCID API|SureChEMBL substructure|Google Patents|EPO data only/i,
    );
  });
});
