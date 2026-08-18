import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SampleReportMobileCommandBar } from "@/components/marketing/sample-report-mobile-command-bar";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

const demoArtifact = {
  compoundName: "succinic acid",
  canonicalSmiles: "OC(=O)CCC(O)=O",
  verdict: "high",
  blockingPatentsCount: 3,
  familiesFlaggedForReviewCount: 2,
  totalPatentsFound: 2417,
  patentsAfterTriage: 47,
  patentsAnalyzed: 5,
  runtimeLabel: "2 min 12 s",
  executiveSummary: "Three active patents present blocking risk.",
  keyFindings: [],
  searchFunnel: [],
  timing: [],
  claimSnapshot: {
    patentId: "US0000000001A1",
    patentTitle: "Fermentation process",
    claimNumber: 1,
    claimStatus: "partially_met",
    elements: [],
  },
  evidenceRows: [],
  provenance: {
    reportId: "rpt_demo_succinic_001",
    generatedAt: "2026-07-01T14:22:13.100Z",
    pipelineVersion: "0.9.4",
    executionProfile: "world_class_adaptive",
    modelNames: ["claude-sonnet-4-20250514"],
    totalInputTokens: 126146,
    totalOutputTokens: 31563,
    estimatedCostUsd: 4.82,
  },
  verification: {
    checks: [],
    issues: [],
    unsupportedVisibleClaims: 0,
    reviewNeededClaims: 1,
  },
  sourceHealth: [],
  analysisFailures: [],
  dataLimitations: [],
  designAround: "Use a downstream process outside the asserted claim scope.",
  invalidityTeaser: "A prior-art reference may support obviousness review.",
  disclaimer: "Synthetic fixture.",
  sourceReference: "Synthetic public fixture",
} satisfies DemoArtifactPayload;

describe("SampleReportMobileCommandBar", () => {
  it("starts as a compact mobile rail with the primary finding action accessible", () => {
    render(<SampleReportMobileCommandBar demoArtifact={demoArtifact} />);

    const toolbar = screen.getByRole("navigation", {
      name: "Sample report command bar",
    });
    expect(toolbar).toHaveClass("sticky", "top-14", "lg:hidden");
    expect(toolbar).not.toHaveClass("fixed");
    expect(toolbar).toHaveAttribute("data-state", "collapsed");
    expect(toolbar).toHaveTextContent("succinic acid sample");
    expect(toolbar).toHaveTextContent("Fictional");
    expect(toolbar).toHaveTextContent("2 flagged");
    expect(
      screen.getByRole("group", {
        name: /2 sample families flagged for review/i,
      }),
    ).toBeInTheDocument();

    const sampleLink = screen.getByRole("link", { name: "Summary" });
    expect(sampleLink).toHaveAttribute("href", "#sample-verdict-packet");
    expect(sampleLink).toHaveClass("min-h-11");
    expect(
      screen.getByRole("button", { name: "Show report sections" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("link", { name: "Claims" }),
    ).not.toBeInTheDocument();
  });

  it("reveals secondary jump targets on demand and collapses after navigation", () => {
    render(<SampleReportMobileCommandBar demoArtifact={demoArtifact} />);

    const toolbar = screen.getByRole("navigation", {
      name: "Sample report command bar",
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Show report sections" }),
    );

    expect(toolbar).toHaveAttribute("data-state", "expanded");
    expect(
      screen.getByRole("button", { name: "Hide report sections" }),
    ).toHaveAttribute("aria-expanded", "true");

    for (const [label, href] of [
      ["Claims", "#sample-claim-chart"],
      ["Sources", "#sample-evidence-ledger"],
      ["Limits", "#sample-verification-limits"],
    ] as const) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("href", href);
      expect(link).toHaveClass("min-h-11");
    }

    fireEvent.click(screen.getByRole("link", { name: "Claims" }));

    expect(toolbar).toHaveAttribute("data-state", "collapsed");
    expect(
      screen.queryByRole("link", { name: "Claims" }),
    ).not.toBeInTheDocument();
  });

  it("truncates long identity and risk copy inside the compact rail", () => {
    const longCompound =
      "N-(4-((7-chloro-6-(longsubstituentchainwithnoobviousbreakpoints)quinazolin-4-yl)oxy)phenyl)-3-hydroxypropanamide";

    render(
      <SampleReportMobileCommandBar
        demoArtifact={{
          ...demoArtifact,
          compoundName: longCompound,
          verdict: "requires_counsel_review",
          blockingPatentsCount: 1234,
          familiesFlaggedForReviewCount: 1234,
          patentsAnalyzed: 9876,
        }}
      />,
    );

    expect(screen.getByText(`${longCompound} sample`)).toHaveClass("truncate");
    expect(screen.getByText(/Fictional · 1234 flagged/u)).toHaveClass(
      "truncate",
    );
  });
});
