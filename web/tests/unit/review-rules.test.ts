import { describe, it, expect } from "vitest";
import { getReviewTier, getPatentReviewTier } from "@/lib/review-rules";

describe("getReviewTier", () => {
  it("never lets raw confidence waive review", () => {
    expect(getReviewTier(0)).toBe("suggest_review");
    expect(getReviewTier(0.7)).toBe("suggest_review");
    expect(getReviewTier(1)).toBe("suggest_review");
  });
});

describe("getPatentReviewTier", () => {
  it("mandates review for high-risk patents regardless of confidence", () => {
    expect(
      getPatentReviewTier({
        risk_level: "high",
        claims_analyzed: [{ confidence: 0.99 }],
      }),
    ).toBe("mandate_review");
  });

  it("mandates review for medium risk regardless of confidence", () => {
    expect(
      getPatentReviewTier({
        risk_level: "medium",
        claims_analyzed: [{ confidence: 0.95 }],
      }),
    ).toBe("mandate_review");

    expect(
      getPatentReviewTier({
        risk_level: "medium",
        claims_analyzed: [{ confidence: 0.9 }],
      }),
    ).toBe("mandate_review");
  });

  it("suggests human review for low risk regardless of confidence", () => {
    expect(
      getPatentReviewTier({
        risk_level: "low",
        claims_analyzed: [{ confidence: 0.92 }],
      }),
    ).toBe("suggest_review");
  });

  it("suggests review when no claims analyzed", () => {
    expect(
      getPatentReviewTier({
        risk_level: "low",
        claims_analyzed: [],
      }),
    ).toBe("suggest_review");
  });

  it("does not average uncalibrated claim confidence into policy", () => {
    expect(
      getPatentReviewTier({
        risk_level: "low",
        claims_analyzed: [{ confidence: 0.95 }, { confidence: 0.5 }],
      }),
    ).toBe("suggest_review"); // avg 0.725
  });
});
