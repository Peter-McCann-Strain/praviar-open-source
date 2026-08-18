import { beforeEach, describe, expect, it } from "vitest";
import {
  MARKETING_COMPOUND_HANDOFF_MAX_LENGTH,
  clearMarketingCompoundHandoff,
  consumeMarketingCompoundHandoff,
  storeMarketingCompoundHandoff,
} from "@/lib/marketing-compound-handoff";

describe("marketing compound handoff", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("stores a validated value in session storage and consumes it once", () => {
    expect(
      storeMarketingCompoundHandoff(
        "  CC(=O)Oc1ccccc1C(=O)O  ",
        sessionStorage,
        1_000,
      ),
    ).toBe(true);

    expect(sessionStorage).toHaveLength(1);
    expect(consumeMarketingCompoundHandoff(sessionStorage, 2_000)).toBe(
      "CC(=O)Oc1ccccc1C(=O)O",
    );
    expect(sessionStorage).toHaveLength(0);
    expect(consumeMarketingCompoundHandoff(sessionStorage, 2_000)).toBe("");
  });

  it("deletes an expired value before returning", () => {
    storeMarketingCompoundHandoff("aspirin", sessionStorage, 1_000);

    expect(
      consumeMarketingCompoundHandoff(
        sessionStorage,
        1_000 + 15 * 60 * 1_000 + 1,
      ),
    ).toBe("");
    expect(sessionStorage).toHaveLength(0);
  });

  it("fails closed for empty, oversized, future-dated, or malformed values", () => {
    expect(storeMarketingCompoundHandoff(" ", sessionStorage, 1_000)).toBe(
      false,
    );
    expect(
      storeMarketingCompoundHandoff(
        "x".repeat(MARKETING_COMPOUND_HANDOFF_MAX_LENGTH + 1),
        sessionStorage,
        1_000,
      ),
    ).toBe(false);

    storeMarketingCompoundHandoff("aspirin", sessionStorage, 2_000);
    expect(consumeMarketingCompoundHandoff(sessionStorage, 1_000)).toBe("");

    sessionStorage.setItem("praviar:marketing-compound-handoff:v1", "{");
    expect(consumeMarketingCompoundHandoff(sessionStorage, 3_000)).toBe("");
    expect(sessionStorage).toHaveLength(0);
  });

  it("can be cleared at the authentication boundary", () => {
    storeMarketingCompoundHandoff("aspirin", sessionStorage, 1_000);
    clearMarketingCompoundHandoff(sessionStorage);
    expect(sessionStorage).toHaveLength(0);
  });
});
