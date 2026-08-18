import { describe, expect, it } from "vitest";

import {
  PROBLEM_TYPE_BASE_URI,
  PROBLEM_TYPES,
  canonicalProblemTypeUri,
} from "@/lib/problem-types";

describe("problem-type contract", () => {
  it("uses the reserved non-dereferenceable authority", () => {
    expect(PROBLEM_TYPE_BASE_URI).toBe("https://problems.praviar.invalid/");
    expect(PROBLEM_TYPES.analysisCapacityExhausted).toBe(
      "https://problems.praviar.invalid/analysis-capacity-exhausted",
    );
  });

  it("accepts only canonical problem types from the reserved authority", () => {
    expect(
      canonicalProblemTypeUri(
        "https://problems.praviar.invalid/service-unavailable",
      ),
    ).toBe("https://problems.praviar.invalid/service-unavailable");
    expect(canonicalProblemTypeUri("about:blank")).toBe("about:blank");

    for (const unsafe of [
      "http://problems.praviar.invalid/service-unavailable",
      "https://problems.praviar.invalid@evil.example/service-unavailable",
      "https://problems.praviar.invalid/service-unavailable?debug=true",
      "https://problems.praviar.invalid/Bad_Slug",
      "not-a-uri",
    ]) {
      expect(canonicalProblemTypeUri(unsafe)).toBeUndefined();
    }
  });
});
