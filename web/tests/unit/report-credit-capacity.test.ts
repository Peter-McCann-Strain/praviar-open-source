import { describe, expect, it } from "vitest";
import { getReportCreditCapacitySnapshot } from "@/lib/report-credit-capacity";

describe("getReportCreditCapacitySnapshot", () => {
  it("uses the backend effective limit when purchased credits were already consumed", () => {
    expect(
      getReportCreditCapacitySnapshot({
        analyses_used: 30,
        analyses_limit: 32,
        included_analyses_limit: 25,
        plan: "starter",
        purchased_credits_balance: 1,
        purchased_credits_used: 6,
      }),
    ).toMatchObject({
      additionalCapacityRemaining: 0,
      consumedCreditBackedRequests: 6,
      creditBackedRemaining: 1,
      effectiveRemaining: 2,
      includedRemaining: 1,
      purchasedCreditsBalance: 1,
      totalCreditBackedCapacity: 7,
    });
  });

  it("keeps lapsed-plan purchased credits visible after allowance downgrade", () => {
    expect(
      getReportCreditCapacitySnapshot({
        analyses_used: 5,
        analyses_limit: 7,
        included_analyses_limit: 3,
        plan: "pro",
        purchased_credits_balance: 2,
        purchased_credits_used: 0,
      }),
    ).toMatchObject({
      additionalCapacityRemaining: 0,
      consumedCreditBackedRequests: 0,
      creditBackedRemaining: 2,
      effectiveRemaining: 2,
      includedRemaining: 0,
      purchasedCreditsBalance: 2,
      totalCreditBackedCapacity: 2,
    });
  });
});
