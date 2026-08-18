import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/marketing/page-event-beacon", () => ({
  PageEventBeacon: () => null,
}));

vi.mock("@/components/landing/pipeline-comparison", () => ({
  PipelineComparison: () => <div data-testid="pipeline-comparison" />,
}));

vi.mock("@/marketing/live-demo", () => ({
  getMarketingDemoArtifact: () => ({
    compoundName: "Succinic acid",
    canonicalSmiles: "O=C(O)CCC(=O)O",
    verdict: "high",
    blockingPatentsCount: 3,
    familiesFlaggedForReviewCount: 1,
    totalPatentsFound: 2417,
    patentsAfterTriage: 47,
    patentsAnalyzed: 5,
    runtimeLabel: "2 min 12 s",
    executiveSummary: "Synthetic executive summary.",
    keyFindings: [],
    searchFunnel: [],
    timing: [],
    claimSnapshot: {
      patentId: "US-DEMO",
      patentTitle: "Synthetic patent",
      claimNumber: 1,
      claimStatus: "met",
      elements: [],
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
    designAround: "Synthetic design-around.",
    invalidityTeaser: "Synthetic invalidity teaser.",
    disclaimer: "Synthetic disclaimer.",
    sourceReference: "Fictional product sample",
  }),
}));

vi.mock("@/components/marketing/sample-report-detail-preview-card", () => ({
  SampleReportDetailPreviewCard: ({
    className,
    compactItemLimit,
    demoArtifact,
    mobileDisclosure,
    mobileSummaryOnly,
    mobileVisualHidden,
  }: {
    className?: string;
    compactItemLimit?: number;
    demoArtifact: { compoundName: string; sourceReference: string };
    mobileDisclosure?: boolean;
    mobileSummaryOnly?: boolean;
    mobileVisualHidden?: boolean;
  }) => (
    <aside
      className={className}
      data-compact-item-limit={compactItemLimit}
      data-mobile-disclosure={mobileDisclosure ? "true" : "false"}
      data-mobile-summary-only={mobileSummaryOnly ? "true" : "false"}
      data-mobile-visual-hidden={mobileVisualHidden ? "true" : "false"}
      data-testid="sample-report-preview"
    >
      {demoArtifact.compoundName}
      <span>{demoArtifact.sourceReference}</span>
    </aside>
  ),
}));

import AdaptiveAgenticPage from "@/app/(marketing)/compare/adaptive-agentic/page";
import DemoPage from "@/app/(marketing)/demo/page";
import ForBiotechFoundersPage from "@/app/(marketing)/for-biotech-founders/page";
import MethodologyPage from "@/app/(marketing)/methodology/page";
import PrivacyPage from "@/app/(marketing)/privacy/page";
import SampleReportsPage from "@/app/(marketing)/sample-reports/page";
import TermsPage from "@/app/(marketing)/terms/page";
import TrustPage from "@/app/(marketing)/trust/page";

describe("secondary marketing pages", () => {
  it("turns /demo into an informational fictional-product walkthrough", () => {
    const { container } = render(<DemoPage />);

    expect(
      screen.getByRole("heading", {
        name: "Inspect a fictional preliminary patent-screening dossier.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-report-hero-field"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("homepage-demo-panel")).toBeInTheDocument();
    expect(screen.getByText("rpt_demo_succinic_001")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Open the fictional sample" })[0],
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getAllByRole("link", { name: "Review the methodology" })[0],
    ).toHaveAttribute("href", "/methodology");
    expect(
      screen.getByRole("heading", {
        name: "Follow the engineering from interface to evidence ledger.",
      }),
    ).toBeInTheDocument();
    expect(container.querySelector('a[href*="sign-up"]')).toBeNull();
    expect(container.querySelector('a[href*="billing"]')).toBeNull();
    expect(
      screen.getByText(/public repository documents the web application/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/this sample is fictional/i)).toBeInTheDocument();
  });

  it("uses the evidence hero visual layer on methodology", () => {
    const { container } = render(<MethodologyPage />);

    expect(
      screen.getByRole("heading", {
        name: "See how a compound becomes a patent-risk brief.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-secondary-hero-field"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("A compound alone is not enough."),
    ).toBeInTheDocument();
    expect(screen.getByText("Stage 01")).toBeInTheDocument();
    expect(screen.getByText("Stage 08")).toBeInTheDocument();
    expect(screen.getByText("The gaps matter too.")).toBeInTheDocument();
    const firstMobileMethodChapter = screen
      .getAllByText("Define the matter")
      .map((element) => element.closest("details"))
      .find((element): element is HTMLDetailsElement => element !== null);
    expect(firstMobileMethodChapter).toHaveAttribute("open");
    expect(
      screen.getAllByRole("link", { name: "Open the fictional sample" })[0],
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getByRole("link", { name: "Review current assurance status" }),
    ).toHaveAttribute("href", "/trust#assurance-heading");
    expect(container.querySelector('a[href*="sign-up"]')).toBeNull();
    expect(container.querySelector('a[href*="billing"]')).toBeNull();
  });

  it("uses an evidence hero and avoids double-padding the adaptive comparison", () => {
    const { container } = render(<AdaptiveAgenticPage />);

    expect(
      screen.getByRole("heading", {
        name: "A closer look when the first answer is not good enough.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-secondary-hero-field"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("pipeline-comparison").parentElement,
    ).not.toHaveClass("p-6");
    expect(screen.getByText("Walkthrough updated")).toBeInTheDocument();
    expect(screen.getByText("July 1, 2026")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open the fictional sample" }),
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getByRole("link", { name: /Review the methodology/ }),
    ).toHaveAttribute("href", "/methodology");
    expect(container.querySelector('a[href*="sign-up"]')).toBeNull();
    expect(screen.queryByText("Start Quick Check")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Start Counsel-Grade Run"),
    ).not.toBeInTheDocument();
  });

  it("puts the report artifact and caveats in the founder hero", () => {
    const { container } = render(<ForBiotechFoundersPage />);

    expect(
      screen.getByRole("heading", {
        name: "Review patent questions before the development plan becomes harder to change.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-report-hero-field"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: /two experienced life-sciences professionals listen to one another/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not Praviar staff, customers, facilities/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not replace a legal opinion/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Expected artifact")).toBeInTheDocument();
    expect(
      screen.getByText(/candidate families, claim support/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Give counsel a defined question and a traceable starting point.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Planned activity")).toBeInTheDocument();
    expect(screen.getByText("Market and timing")).toBeInTheDocument();
    expect(screen.getByText("Product boundary")).toBeInTheDocument();
    expect(
      screen.getByText(/does not decide infringement, validity/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Open the fictional sample" })[0],
    ).toHaveClass("w-full", "sm:w-auto");
    expect(
      screen.getByRole("link", { name: "Trust and deployment" }),
    ).toHaveAttribute("href", "/trust");
    expect(
      screen.getByRole("heading", {
        name: "Evaluate the format without a purchasing claim.",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\$\d+/)).not.toBeInTheDocument();
    expect(screen.queryByText(/indicative pricing/i)).not.toBeInTheDocument();
    expect(
      screen.getAllByText(/working open-source research system/i).length,
    ).toBeGreaterThan(0);
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
  });

  it("leads sample reports with the artifact preview and an honest proof boundary", () => {
    const { container } = render(<SampleReportsPage />);

    expect(
      screen.getByRole("heading", {
        name: "See the report before you run one.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-report-hero-field"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("sample-report-preview")).toBeInTheDocument();
    expect(screen.getByTestId("sample-report-preview")).toHaveAttribute(
      "data-compact-item-limit",
      "1",
    );
    expect(screen.getByTestId("sample-report-preview")).toHaveAttribute(
      "data-mobile-summary-only",
      "true",
    );
    expect(screen.getByTestId("sample-report-preview")).toHaveAttribute(
      "data-mobile-visual-hidden",
      "true",
    );
    expect(screen.getByTestId("sample-index-supporting-metrics")).toHaveClass(
      "hidden",
      "lg:grid",
    );
    expect(screen.getByText("Read the sample honestly")).toBeInTheDocument();
    expect(screen.getByText("What you can inspect")).toBeInTheDocument();
    expect(screen.getByText("What it does not prove")).toBeInTheDocument();
    expect(
      screen.getByText(/does not replace a legal opinion/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/live proof/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/live report surface/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /open the sample dossier/i }),
    ).toHaveClass("w-full", "sm:w-auto");
    const fixtureIdentifiers = screen
      .getAllByText("Fictional product sample")
      .filter((element) => element.classList.contains("font-mono"));
    expect(fixtureIdentifiers.length).toBeGreaterThan(0);
    for (const identifier of fixtureIdentifiers) {
      expect(identifier).toHaveClass("[overflow-wrap:anywhere]");
      expect(identifier).not.toHaveClass("break-all");
    }
  });

  it("turns trust evidence into a governed control artifact", () => {
    const { container } = render(<TrustPage />);

    expect(
      screen.getByRole("heading", {
        name: "Know what Praviar can protect and prove before you use it.",
      }),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".praviar-trust-hero-field"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("trust-control-visual")).toHaveTextContent(
      "The work stays visible",
    );
    expect(screen.getByTestId("trust-control-visual")).toHaveTextContent(
      "Claims, citations, source health",
    );
    expect(screen.getByTestId("trust-boundary-artifact")).toHaveTextContent(
      "Qualified counsel review",
    );
    expect(
      screen.getByRole("link", { name: "Open the fictional sample" }),
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getByRole("link", { name: "Read the privacy notice" }),
    ).toHaveAttribute("href", "/privacy");
    expect(
      screen.getAllByText(
        /integration references in source code, not active subprocessors/i,
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/working open-source research system/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/SOC 2 certified/i)).toBeInTheDocument();
    expect(screen.queryByText(/visual system asset/i)).not.toBeInTheDocument();
  });

  it("renders privacy as a non-binding research-preview notice", async () => {
    const { container } = render(<PrivacyPage />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Research Preview Privacy Notice",
      }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("main")).toHaveLength(0);
    const desktopLegalDocument = screen.getByTestId("legal-document");
    expect(desktopLegalDocument).toBeInTheDocument();
    expect(screen.getByTestId("mobile-legal-document")).toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("overflow-x-clip");
    expect(container.firstElementChild).not.toHaveClass("overflow-hidden");
    expect(
      screen.getByRole("navigation", { name: "Legal document sections" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Jump to a section" }),
    ).toHaveAttribute("aria-controls", "mobile-legal-document-section-links");
    expect(
      screen.getByRole("navigation", {
        name: "Mobile legal document sections",
      }),
    ).toHaveAttribute("id", "mobile-legal-document-section-links");
    const mobileSectionNav = screen.getByTestId("mobile-legal-section-nav");
    const mobileDataSecurity = document.getElementById("mobile-data-security");
    if (!(mobileDataSecurity instanceof HTMLDetailsElement)) {
      throw new Error("Expected the mobile Data Security disclosure");
    }
    expect(mobileDataSecurity).not.toHaveAttribute("open");
    mobileSectionNav.setAttribute("open", "");
    fireEvent.click(
      within(mobileSectionNav).getByRole("link", {
        name: "6. Security and confidentiality boundary",
      }),
    );
    expect(mobileSectionNav).not.toHaveAttribute("open");
    expect(mobileDataSecurity).toHaveAttribute("open");
    expect(window.location.hash).toBe("#mobile-data-security");
    await waitFor(() => {
      expect(
        within(mobileDataSecurity).getByRole("button", {
          name: "6. Security and confidentiality boundary",
        }),
      ).toHaveFocus();
    });
    expect(screen.getByTestId("legal-document-section-nav-shell")).toHaveClass(
      "sticky",
      "top-20",
      "lg:top-28",
    );
    for (const link of screen.getAllByRole("link", {
      name: "2. What the preview contains",
    })) {
      expect(link).toHaveClass(
        "min-h-11",
        "focus-visible:ring-brand-primary/70",
      );
    }
    expect(screen.getAllByText("Last updated: August 13, 2026")).toHaveLength(
      1,
    );
    expect(
      screen.getByRole("link", { name: "Review evidence boundaries" }),
    ).toHaveAttribute("href", "/trust");
    expect(
      screen.getByRole("heading", {
        name: "6. Security and confidentiality boundary",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Not represented by this page"),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        "Repository references, not a subprocessor list",
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /publishes no production retention schedule/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /does not publish a verified controller or privacy contact/i,
      ),
    ).toBeInTheDocument();
    const desktopIntegrationTable = within(desktopLegalDocument).getByTestId(
      "integration-status-table",
    );
    expect(desktopIntegrationTable.querySelector("thead")).toHaveClass(
      "hidden",
      "md:table-header-group",
    );
    expect(desktopIntegrationTable.querySelector("table")).toHaveClass(
      "table-fixed",
    );
    const mobileIntegrationCards = within(
      screen.getByTestId("mobile-legal-document"),
    ).getByTestId("integration-status-mobile-cards");
    expect(within(mobileIntegrationCards).getAllByRole("button")).toHaveLength(
      5,
    );
    for (const integrationCard of mobileIntegrationCards.querySelectorAll(
      "details",
    )) {
      expect(integrationCard).toHaveClass("group/integration");
    }
    for (const collapsedIcon of within(mobileIntegrationCards).getAllByText(
      "＋",
    )) {
      expect(collapsedIcon).toHaveClass("group-open/integration:hidden");
    }
    for (const expandedIcon of within(mobileIntegrationCards).getAllByText(
      "−",
    )) {
      expect(expandedIcon).toHaveClass("group-open/integration:inline");
    }
    expect(
      within(desktopIntegrationTable).getByRole("rowheader", {
        name: "Anthropic",
      }),
    ).toHaveClass("whitespace-nowrap");
    expect(
      within(desktopIntegrationTable).getByText(
        /No production activation, contract, training posture/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /engineering controls are not proof of a particular deployment/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /not represented as the privacy policy of an operating service/i,
      ),
    ).toBeInTheDocument();
    expect(container.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
    expect(screen.queryByText(/privacy@praviar\.com/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/365 days|7 years|30-day recovery/i),
    ).not.toBeInTheDocument();
    expect(desktopLegalDocument.textContent).not.toMatch(
      /Praviar operates|we collect|we process your data|we retain/i,
    );
  });

  it("renders a non-binding use notice with no service or legal-advice claim", () => {
    const { container } = render(<TermsPage />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Research Preview Use Notice",
      }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll("main")).toHaveLength(0);
    const desktopLegalDocument = screen.getByTestId("legal-document");
    expect(desktopLegalDocument).toBeInTheDocument();
    expect(screen.getByTestId("mobile-legal-document")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Legal document sections" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Last updated: August 13, 2026")).toHaveLength(
      1,
    );
    expect(
      screen.getByRole("link", { name: "Review the methodology" }),
    ).toHaveAttribute("href", "/methodology");
    expect(
      within(desktopLegalDocument).getByText(
        "No service. No contract. No legal advice.",
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /does not create a service contract, customer relationship, subscription/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /does not offer an account, plan, subscription, report credit/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/no legal advice/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", {
        name: "5. Source licence and third-party rights",
      }),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /Apache-2\.0 licence in the repository—not this notice—governs/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "8. Security and deployment boundary",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "10. No service promises or online liability terms",
      }),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /does not attempt to waive rights or limit liability/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "11. No contracting entity, notice address, or governing law",
      }),
    ).toBeInTheDocument();
    expect(
      within(desktopLegalDocument).getByText(
        /No such term should be inferred from repository metadata/i,
      ),
    ).toBeInTheDocument();
    expect(container.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
    expect(screen.queryByText(/legal@praviar\.com/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/State of Delaware/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/\$\d|billed monthly|billed annually/i),
    ).not.toBeInTheDocument();
    expect(desktopLegalDocument.textContent).not.toMatch(
      /you agree to be bound|subscriptions are billed|Praviar grants your organization|continued use.*constitutes acceptance/i,
    );
  });
});
