import { isValidElement, type ReactElement } from "react";
import { describe, expect, it } from "vitest";

import LegacyReportRoute from "@/app/(dashboard)/reports/[id]/page";
import { LegacyReportResolver } from "@/components/report/legacy-report-resolver";
import {
  buildLegacyReportRedirectPath,
  resolveLegacyReportAnalysisId,
} from "@/lib/legacy-report-redirect";

describe("legacy report route", () => {
  it.each([
    ["demo", "ana_demo_001"],
    ["sample", "ana_demo_001"],
    ["demo-analysis-001", "ana_demo_001"],
    ["rpt_ana_demo_001", "ana_demo_001"],
    ["rpt_ana_case_123", "ana_case_123"],
  ])("maps deterministic reference %s to %s", (reference, analysisId) => {
    expect(resolveLegacyReportAnalysisId(reference)).toBe(analysisId);
  });

  it("does not assume an opaque report UUID is an analysis UUID", () => {
    const reportId = "5011f7bd-abf4-409a-b78d-c1d67ee804aa";

    expect(resolveLegacyReportAnalysisId(reportId)).toBe(reportId);
  });

  it("preserves deep-link query parameters for deterministic redirects", () => {
    expect(
      buildLegacyReportRedirectPath("rpt_ana_case_123", {
        ai_context: "blocker_brief",
        tab: "patents",
      }),
    ).toBe(
      "/analyses/ana_case_123/report?ai_context=blocker_brief&tab=patents",
    );
  });

  it("renders the authenticated resolver for opaque report references", async () => {
    const reportId = "5011f7bd-abf4-409a-b78d-c1d67ee804aa";
    const route = await LegacyReportRoute({
      params: Promise.resolve({ id: reportId }),
    });

    expect(isValidElement(route)).toBe(true);
    const resolver = (route as ReactElement<{ children: ReactElement }>).props
      .children;
    expect(resolver.type).toBe(LegacyReportResolver);
    expect(resolver.props).toEqual({ id: reportId });
  });
});
