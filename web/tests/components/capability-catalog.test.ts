import { describe, expect, it } from "vitest";

import {
  CAPABILITY_GROUPS,
  COMMAND_CAPABILITY_ITEMS,
  DEMO_COUNSEL_WORKSPACE_HREF,
  DEMO_SCRIPT_STEPS,
  DEMO_STORIES,
  getCapabilityCatalog,
} from "@/components/capabilities/capability-catalog";

describe("capability catalog", () => {
  it("links the analytics capability to its dedicated surface", () => {
    const analytics = CAPABILITY_GROUPS.flatMap((group) => group.items).find(
      (item) => item.label === "Admin analytics",
    );

    expect(analytics?.href).toBe("/admin/analytics");
  });
  it("keeps every backend capability routable and command-searchable", () => {
    expect(COMMAND_CAPABILITY_ITEMS.length).toBeGreaterThanOrEqual(12);

    for (const item of COMMAND_CAPABILITY_ITEMS) {
      expect(item.href).toMatch(/^\//);
      expect(item.commandValue.trim()).not.toBe("");
      expect(item.endpoints.length).toBeGreaterThan(0);
      expect(item.groupTitle.trim()).not.toBe("");
    }
  });

  it("covers the full demo workflow from report workspace through review, monitor, export, and admin surfaces", () => {
    const labels = COMMAND_CAPABILITY_ITEMS.map((item) => item.label);

    expect(labels).toEqual(
      expect.arrayContaining([
        "High-risk demo case",
        "Governed evidence search",
        "AI review workspace",
        "Review queue",
        "Reviewer decisions",
        "Patent monitors",
        "Exports and sharing",
        "Admin analytics",
      ]),
    );

    expect(
      COMMAND_CAPABILITY_ITEMS.find(
        (item) => item.label === "High-risk demo case",
      )?.href,
    ).toBe(DEMO_COUNSEL_WORKSPACE_HREF);
    expect(
      COMMAND_CAPABILITY_ITEMS.find(
        (item) => item.label === "Reviewer decisions",
      )?.endpoints,
    ).toContain("POST /analyses/{analysis_id}/decisions");
  });

  it("keeps demo stories and runbook steps aligned to actual command center routes", () => {
    const capabilityRoutes = new Set(
      CAPABILITY_GROUPS.flatMap((group) =>
        group.items.map((item) => item.href),
      ),
    );

    expect(DEMO_STORIES.map((story) => story.audience)).toEqual(
      expect.arrayContaining(["Counsel", "Founder", "Diligence", "Operations"]),
    );

    for (const step of DEMO_SCRIPT_STEPS) {
      expect(step.href).toMatch(/^\//);
      expect(
        capabilityRoutes.has(step.href) ||
          step.href === "/reviews" ||
          step.href === "/monitors",
      ).toBe(true);
    }
  });

  it("keeps live-mode capability links away from fixture-only demo workspaces", () => {
    const liveCatalog = getCapabilityCatalog({
      localDemoWorkspaceEnabled: false,
    });
    const liveHrefs = [
      liveCatalog.showcaseHref,
      ...liveCatalog.demoStories.map((story) => story.href),
      ...liveCatalog.demoScriptSteps.map((step) => step.href),
      ...liveCatalog.commandCapabilityItems.map((item) => item.href),
    ];

    expect(liveCatalog.showcaseHref).toBe("/analyses");
    expect(liveHrefs.some((href) => href.includes("ana_demo_"))).toBe(false);
    expect(liveHrefs).toEqual(
      expect.arrayContaining([
        "/analyses/new",
        "/analyses",
        "/batch",
        "/monitors",
      ]),
    );
  });
});
