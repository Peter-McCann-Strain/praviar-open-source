import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const principalState = vi.hoisted(() => ({
  canCreateAnalysis: true,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("@/components/brand", () => ({
  EvidenceLaunchVisual: ({ label }: { label: string }) => (
    <div aria-label={label} data-testid="evidence-launch-visual" />
  ),
}));

vi.mock("@/components/shared/onboarding-tooltip", () => ({
  OnboardingTooltip: () => <div data-testid="onboarding-tooltip" />,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: principalState.canCreateAnalysis,
    },
  }),
}));

import { DashboardPageHeader } from "@/components/dashboard/page-header";
import { EmptyDashboard } from "@/components/dashboard/empty-dashboard";

describe("dashboard entry actions", () => {
  beforeEach(() => {
    principalState.canCreateAnalysis = true;
  });

  it("renders empty-state primary actions as links without nested buttons", () => {
    render(<EmptyDashboard />);

    const startLink = screen.getByRole("link", { name: "Start New Analysis" });

    expect(startLink).toHaveAttribute("href", "/analyses/new");
    expect(within(startLink).queryByRole("button")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Review Queue" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("auth-mobile-proof")).not.toBeInTheDocument();
  });

  it("places authoritative setup recovery before feature proof", () => {
    render(
      <EmptyDashboard
        setupReadiness={<div data-testid="authoritative-setup" />}
      />,
    );

    const hero = screen.getByTestId("empty-dashboard-hero");
    const setup = screen.getByTestId("authoritative-setup");
    const featureProof = screen.getByTestId("empty-dashboard-feature-proof");
    expect(
      hero.compareDocumentPosition(setup) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      setup.compareDocumentPosition(featureProof) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("renders dashboard header action as a link without nested controls", () => {
    const { container } = render(<DashboardPageHeader />);

    const newAnalysisLink = screen.getByRole("link", { name: "New Analysis" });
    const commandDeck = container.querySelector(
      "[data-praviar-dashboard-command-deck='app-evidence']",
    );
    const commandArt = container.querySelector(".praviar-command-deck-art");
    const markFrame = container.querySelector(".h-14.w-14");

    expect(newAnalysisLink).toHaveAttribute("href", "/analyses/new");
    expect(
      within(newAnalysisLink).queryByRole("button"),
    ).not.toBeInTheDocument();
    expect(commandDeck).toBeInTheDocument();
    expect(commandDeck).toHaveClass("praviar-dashboard-command-deck");
    expect(commandArt).toBeInTheDocument();
    expect(markFrame?.className).toContain("rounded-lg");
    expect(markFrame?.className).not.toContain("rounded-2xl");
  });

  it("distinguishes workspace totals from the recent metric window", () => {
    render(
      <DashboardPageHeader
        totalAnalyses={250}
        runningCount={3}
        reviewCount={12}
        sampleWindowSize={100}
        latestUpdatedAt={new Date().toISOString()}
      />,
    );

    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("250")).toBeInTheDocument();
    expect(screen.getByText("All analyses")).toBeInTheDocument();
    expect(screen.getAllByText("Latest 100 analyses")).toHaveLength(2);
    expect(screen.getByText("Metric window")).toBeInTheDocument();
    expect(screen.getByText("Latest 100")).toBeInTheDocument();
    expect(
      screen.getByText("Workspace").closest("[role='group']"),
    ).not.toHaveClass("hidden");
    expect(screen.getByText("Updated").closest("[role='group']")).toHaveClass(
      "hidden",
      "sm:block",
    );
    expect(
      screen.getByText("Metric window").closest("[role='group']"),
    ).toHaveClass("hidden", "sm:block");
  });

  it("gives read-only clients a useful shared-workspace path without export promises", () => {
    principalState.canCreateAnalysis = false;

    render(<EmptyDashboard />);

    expect(screen.getByText("Your shared FTO workspace")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View sample report" }),
    ).toHaveAttribute("href", "/sample-reports/example-molecule-alpha");
    expect(
      screen.getByRole("link", { name: "Get access help" }),
    ).toHaveAttribute("href", "/help#contact");
    expect(
      screen.queryByRole("link", { name: "Open analysis library" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Start New Analysis" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Export PDF with full citations/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("onboarding-tooltip")).not.toBeInTheDocument();
  });
});
