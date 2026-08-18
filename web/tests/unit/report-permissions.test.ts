import { describe, expect, it } from "vitest";
import {
  canAccessFullReport,
  canManageReportCollaboration,
  getReportAccessHref,
  getReportAccessHrefWithQuery,
  normalizeApplicationRole,
} from "@/lib/report-permissions";

describe("report permissions", () => {
  it.each(["admin", "attorney", "org:admin", "ORG:ATTORNEY"])(
    "allows governed collaboration for %s",
    (role) => {
      expect(canManageReportCollaboration(role)).toBe(true);
    },
  );

  it.each(["scientist", "client", null, undefined])(
    "fails closed for %s",
    (role) => {
      expect(canManageReportCollaboration(role)).toBe(false);
    },
  );

  it("normalizes Clerk-style role prefixes", () => {
    expect(normalizeApplicationRole(" org:Attorney ")).toBe("attorney");
  });

  it("routes counsel to the workspace and other roles to the authorized summary", () => {
    expect(getReportAccessHref("analysis 1", "client")).toBe(
      "/analyses/analysis%201/report/summary",
    );
    expect(getReportAccessHref("analysis-2", "scientist")).toBe(
      "/analyses/analysis-2/report/summary",
    );
    expect(getReportAccessHref("analysis-3", "attorney")).toBe(
      "/analyses/analysis-3/report",
    );
    expect(getReportAccessHref("analysis-4", "scientist", false)).toBe(
      "/analyses/analysis-4/report",
    );
    expect(getReportAccessHref("analysis-5", "scientist", true)).toBe(
      "/analyses/analysis-5/report/summary",
    );
    expect(canAccessFullReport("client", false)).toBe(false);
  });

  it("keeps deep-link context only for principals authorized for the full workspace", () => {
    const query = {
      tab: "patents",
      patent: "US123",
    };

    expect(
      getReportAccessHrefWithQuery("analysis-1", "scientist", true, query),
    ).toBe("/analyses/analysis-1/report/summary");
    expect(
      getReportAccessHrefWithQuery("analysis-1", "scientist", false, query),
    ).toBe("/analyses/analysis-1/report?tab=patents&patent=US123");
  });
});
