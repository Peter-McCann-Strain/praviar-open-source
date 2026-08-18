import { fireEvent, render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarketingHomePage } from "@/components/marketing/home-page";
import {
  formatFictionalFamiliesFlaggedForReview,
  getSamplePriorityLabel,
} from "@/components/marketing/home-page-helpers";
import type { DemoArtifactPayload } from "@/marketing/live-demo";

vi.mock("motion/react", async () => {
  const { createMotionMock } = await import("../helpers/mock-motion");
  return {
    ...createMotionMock(),
    useReducedMotion: () => false,
  };
});

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/charts/search-funnel", () => ({
  SearchFunnel: () => <div>SearchFunnel</div>,
}));

vi.mock("@/components/charts/timing-waterfall", () => ({
  TimingWaterfall: () => <div>TimingWaterfall</div>,
}));

vi.mock("@/components/shared/risk-badge", () => ({
  RiskBadge: ({ label, risk }: { label?: string; risk: string }) => (
    <div>{label ?? `${risk} badge`}</div>
  ),
}));

const demoArtifact: DemoArtifactPayload = {
  compoundName: "Succinic acid",
  canonicalSmiles: "OC(=O)CCC(O)=O",
  verdict: "medium",
  blockingPatentsCount: 0,
  familiesFlaggedForReviewCount: 1,
  totalPatentsFound: 2417,
  patentsAfterTriage: 47,
  patentsAnalyzed: 5,
  runtimeLabel: "2 min 12 s",
  executiveSummary:
    "A potential fictional overlap requires qualified review.\n\nSecond paragraph.",
  keyFindings: ["Finding 1", "Finding 2", "Finding 3"],
  evidenceRows: [
    {
      patentId: "US1234567",
      title: "Fermentation process",
      assignee: "Example Bio",
      expiryDate: "2034-04-12",
      riskLevel: "medium",
      claimReference: "Claim 1 · not met",
      rationale:
        "Lead claim evidence ties the blocker to the production route.",
      sourceLabel: "2 fixture sources",
      sourceUrl: "#sample-evidence-ledger",
      sourceTraceId: "fixture-trace-US1234567",
      sourcePosture: "Synthetic fixture record",
      sourcesFoundIn: ["surechembl", "bigquery"],
      rank: 1,
      score: 0.89,
      filterReason: "",
      triageReason: "Relevant fermentation claim.",
      triageConfidence: 0.94,
      selectionReason: "Selected for claim-level analysis.",
      selectedForAnalysis: true,
    },
  ],
  searchFunnel: [
    { stage: "Discovered", count: 2417 },
    { stage: "Triaged", count: 47 },
  ],
  timing: [
    { step: "Resolve", duration_seconds: 12 },
    { step: "Search", duration_seconds: 44 },
  ],
  claimSnapshot: {
    patentId: "US1234567",
    patentTitle: "Fermentation process",
    claimNumber: 1,
    claimStatus: "not_met",
    elements: [
      {
        label: "Element 1",
        elementText: "A recombinant prokaryotic microorganism",
        status: "met",
        reasoning: "The process uses recombinant E. coli.",
        confidence: 0.9,
        evidence: "Evidence A",
        traceId: "assertion-element-1",
        sourceCitation: "US1234567 claim 1",
        sourceExcerpt: "E. coli is prokaryotic.",
        supportStatus: "supported",
        reviewRequired: false,
      },
      {
        label: "Element 2",
        elementText: "A yield threshold",
        status: "not_met",
        reasoning: "The process falls below the threshold.",
        confidence: 0.84,
        evidence: "Evidence B",
        traceId: "assertion-element-2",
        sourceCitation: "US1234567 claim 1",
        sourceExcerpt: "Yield threshold text.",
        supportStatus: "supported",
        reviewRequired: false,
      },
    ],
  },
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
    reviewNeededClaims: 0,
  },
  sourceHealth: [],
  analysisFailures: [],
  dataLimitations: [],
  designAround: "Try a fermentation route that avoids the claimed organism.",
  invalidityTeaser: "Potential written-description weakness.",
  disclaimer: "Demo disclaimer",
  sourceReference: "Synthetic public fixture",
};

describe("MarketingHomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("presents an informational public path with a clear artifact", () => {
    const { container } = render(
      <MarketingHomePage demoArtifact={demoArtifact} />,
    );

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "See which patent families may deserve attention before the programme advances.",
      }),
    ).toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute(
      "data-public-readiness",
      "informational_only",
    );
    expect(screen.getByTestId("homepage-public-preview")).toHaveTextContent(
      "Expected artifact",
    );
    expect(screen.getByTestId("homepage-public-preview")).toHaveTextContent(
      "Current research preview",
    );
    expect(screen.getByTestId("homepage-public-preview")).toHaveTextContent(
      "source gaps",
    );
    expect(
      screen.getAllByRole("link", { name: "Open the fictional sample" })[0],
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getAllByRole("link", { name: "Review the methodology" })[0],
    ).toHaveAttribute("href", "/methodology");
    expect(
      screen.getByTestId("homepage-proof-mobile-summary"),
    ).toHaveTextContent("questions for counsel");
    expect(
      screen.getAllByText("Medium sample priority").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("High sample priority")).not.toBeInTheDocument();
    expect(
      screen.getAllByText("1 fictional family flagged for review").length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(/0 fictional families flagged/i),
    ).not.toBeInTheDocument();
    const dossierMetrics = screen.getByTestId("fto-dossier-metrics");
    expect(dossierMetrics).toHaveTextContent(
      "Fictional families flagged for review",
    );
    expect(dossierMetrics).toHaveTextContent("1");
  });

  it("does not expose signup, billing, or purchasing actions", () => {
    render(<MarketingHomePage demoArtifact={demoArtifact} />);

    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href") ?? "").not.toMatch(
        /(?:sign-up|billing|checkout)/i,
      );
    }
    expect(
      screen.queryByRole("link", {
        name: /run|buy|checkout|create (?:a )?workspace/i,
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/working open-source research system/).length,
    ).toBeGreaterThan(0);
  });

  it("keeps trust and the open-source project boundary visible", () => {
    render(<MarketingHomePage demoArtifact={demoArtifact} />);

    const trustBand = screen.getByTestId("homepage-trust-band");
    expect(trustBand).toHaveTextContent(
      "Know what the public preview can and cannot establish.",
    );
    expect(
      within(trustBand).getByRole("link", {
        name: /Review deployment limits/i,
      }),
    ).toHaveAttribute("href", "/trust");

    const project = screen.getByTestId("project-surface-grid");
    expect(project).toHaveTextContent("Next.js workbench");
    expect(project).toHaveTextContent("FastAPI service");
    expect(project).toHaveTextContent("Research pipeline");
    expect(project).toHaveTextContent("Evaluation system");
  });

  it("keeps the sample artifact switcher keyboard accessible", () => {
    render(<MarketingHomePage demoArtifact={demoArtifact} />);

    const tablist = screen.getByRole("tablist", {
      name: "Sample report views",
    });
    const summaryTab = within(tablist).getByRole("tab", { name: /summary/i });
    const claimTab = within(tablist).getByRole("tab", { name: /claim/i });
    const runTab = within(tablist).getByRole("tab", { name: /run/i });

    expect(summaryTab).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(summaryTab, { key: "ArrowRight" });
    expect(claimTab).toHaveAttribute("aria-selected", "true");
    expect(claimTab).toHaveFocus();

    fireEvent.keyDown(claimTab, { key: "End" });
    expect(runTab).toHaveAttribute("aria-selected", "true");
    expect(runTab).toHaveFocus();

    fireEvent.keyDown(runTab, { key: "Home" });
    expect(summaryTab).toHaveAttribute("aria-selected", "true");
    expect(summaryTab).toHaveFocus();
  });
});

describe("homepage canonical sample labels", () => {
  it("keeps priority and flagged-family language explicit at boundaries", () => {
    expect(getSamplePriorityLabel("medium")).toBe("Medium sample priority");
    expect(getSamplePriorityLabel("clear")).toBe("No overlap in sample");
    expect(getSamplePriorityLabel("requires_counsel_review")).toBe(
      "Sample review status pending",
    );
    expect(formatFictionalFamiliesFlaggedForReview(0)).toBe(
      "0 fictional families flagged for review",
    );
    expect(formatFictionalFamiliesFlaggedForReview(1)).toBe(
      "1 fictional family flagged for review",
    );
    expect(formatFictionalFamiliesFlaggedForReview(2)).toBe(
      "2 fictional families flagged for review",
    );
  });
});
