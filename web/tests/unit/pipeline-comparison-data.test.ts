import { describe, expect, it } from "vitest";

import {
  ADAPTIVE_TIMELINE_TRACE,
  MAX_DELAY,
  METRICS,
  STEP_STYLES,
  TIMELINE_CONFIG,
} from "@/components/landing/pipeline-comparison-data";

describe("pipeline-comparison data", () => {
  it("keeps the public import surface intact", () => {
    expect(ADAPTIVE_TIMELINE_TRACE).toHaveLength(12);
    expect(MAX_DELAY).toBe(7.6);
    expect(TIMELINE_CONFIG.label).toBe("Adaptive Evidence Timeline");
    expect(TIMELINE_CONFIG.tagline).toContain("One path");
    expect(METRICS).toHaveLength(4);
    expect(STEP_STYLES.risk.iconColor).toBe("text-success-emphasis");
  });

  it("keeps trace content aligned with the animation timing", () => {
    expect(ADAPTIVE_TIMELINE_TRACE[0]).toMatchObject({
      type: "input",
      text: "Compound + patent claims received",
      delay: 0,
    });
    expect(ADAPTIVE_TIMELINE_TRACE[3]).toMatchObject({
      type: "critique",
      text: "Evidence gap identified: one claim term needs specification support",
      delay: 1.8,
    });
    expect(ADAPTIVE_TIMELINE_TRACE.at(-1)).toMatchObject({
      type: "complete",
      text: "Governed escalation record ready for counsel handoff",
      delay: 7.6,
    });
  });

  it("does not reintroduce public mode-race language", () => {
    const text = ADAPTIVE_TIMELINE_TRACE.map((step) => step.text).join(" ");
    expect(text).not.toMatch(
      /single_pass|agentic|reasoning|fetch_specification|search_spec_definitions|Self-critique/i,
    );
  });
});
