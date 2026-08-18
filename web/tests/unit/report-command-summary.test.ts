import { describe, expect, it } from "vitest";

import { getReportReference } from "@/components/report-page/report-command-summary";

describe("getReportReference", () => {
  it("returns the canonical report identifier", () => {
    expect(getReportReference({ report_id: "PRV-2026-0142" })).toBe(
      "PRV-2026-0142",
    );
  });

  it("normalizes surrounding identifier whitespace", () => {
    expect(getReportReference({ report_id: "  rpt_demo_succinic_001  " })).toBe(
      "rpt_demo_succinic_001",
    );
  });

  it("fails closed when the required report identifier is empty", () => {
    expect(() => getReportReference({ report_id: "   " })).toThrow(
      "Report identifier is unavailable",
    );
  });
});
