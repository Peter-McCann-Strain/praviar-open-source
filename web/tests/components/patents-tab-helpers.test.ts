import { describe, expect, it } from "vitest";
import type { FTOReport } from "@praviar/shared-types";

import { getPatentRows } from "@/components/report/patents-tab-helpers";

describe("getPatentRows", () => {
  it("keeps absent report relevance explicit instead of coercing it to zero", () => {
    const patentAnalysis = {
      patent_id: "WO0000000004A1",
      title: "Solid forms of an antiviral compound",
      assignee: "Fictional Helix Therapeutics",
      risk_level: "high",
    } as FTOReport["patent_analyses"][number];
    const report = {
      patent_analyses: [patentAnalysis],
      patent_details: {
        WO0000000004A1: {
          claims_text: "Claim 1",
        },
      },
    } as unknown as FTOReport;

    expect(getPatentRows(report, report.patent_analyses)).toEqual([
      expect.objectContaining({
        patentNumber: "WO0000000004A1",
        relevanceScore: null,
      }),
    ]);
  });

  it("uses a report-supplied relevance score when present", () => {
    const patentAnalysis = {
      patent_id: "US0000000001A1",
      title: "Formulation patent",
      assignee: "Example Pharma",
      risk_level: "medium",
    } as FTOReport["patent_analyses"][number];
    const report = {
      patent_analyses: [patentAnalysis],
      patent_details: {
        US0000000001A1: {
          confidence_score: 0.82,
        },
      },
    } as unknown as FTOReport;

    expect(
      getPatentRows(report, report.patent_analyses)[0].relevanceScore,
    ).toBe(82);
  });
});
