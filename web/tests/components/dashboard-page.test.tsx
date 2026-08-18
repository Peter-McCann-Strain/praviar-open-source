import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api-client";

const mockUseAuthToken = vi.fn();
const mockUseAnalyses = vi.fn();
const mockUseBillingStatus = vi.fn();

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-analysis", () => ({
  useAnalyses: (...args: unknown[]) => mockUseAnalyses(...args),
}));

vi.mock("@/hooks/use-billing", () => ({
  useBillingStatus: () => mockUseBillingStatus(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  canAccessWorkspaceHref: () => true,
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: true,
      can_view_billing: true,
      can_view_review_queue: true,
      role: "admin",
    },
  }),
}));

vi.mock("@/components/dashboard/legal-review-workload-panel", () => ({
  LegalReviewWorkloadPanel: () => (
    <div data-testid="legal-review-workload-panel" />
  ),
}));

vi.mock("@/components/dashboard/ai-command-panel", () => ({
  AiCommandPanel: () => <div data-testid="dashboard-ai-command-panel" />,
}));

vi.mock("@/components/dashboard/risk-activity-section", () => ({
  RiskActivitySection: () => <div data-testid="risk-activity-section" />,
}));

vi.mock("@/components/dashboard/running-pipelines-alert", () => ({
  RunningPipelinesAlert: () => <div data-testid="running-pipelines-alert" />,
}));

vi.mock("@/components/dashboard/setup-readiness-panel", () => ({
  SetupReadinessPanel: ({
    token,
    compact,
  }: {
    token: string | null;
    compact?: boolean;
  }) => (
    <div
      data-testid="setup-readiness-panel"
      data-token={token}
      data-compact={compact ? "true" : "false"}
    />
  ),
}));

vi.mock("@/components/dashboard/page-header", () => ({
  DashboardPageHeader: () => <div data-testid="dashboard-page-header" />,
}));

vi.mock("@/components/shared/onboarding-tooltip", () => ({
  OnboardingTooltip: () => <div data-testid="onboarding-tooltip" />,
}));

vi.mock("@/components/dashboard/empty-dashboard", () => ({
  EmptyDashboard: ({
    setupReadiness,
  }: {
    setupReadiness?: React.ReactNode;
  }) => (
    <div data-testid="empty-dashboard">
      <div data-testid="empty-dashboard-hero" />
      {setupReadiness}
      <div data-testid="empty-dashboard-feature-proof" />
    </div>
  ),
}));

import DashboardPage from "@/app/(dashboard)/dashboard/page";

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("tok");
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_1",
        stripe_subscription_id: "sub_1",
        subscription_status: "active",
        current_period_start: "2026-07-01T00:00:00.000Z",
        current_period_end: "2026-08-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      isLoading: false,
    });
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          {
            id: "ana-1",
            compound_input: "aspirin",
            compound_name: "Aspirin",
            compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
            status: "completed",
            current_step: 8,
            progress_pct: 100,
            overall_risk: "high",
            blocking_patents_count: 1,
            total_patents_found: 12,
            executive_summary: "Blocking exposure remains.",
            estimated_cost_usd: 4,
            pipeline_duration_seconds: 180,
            flagged_for_review: true,
            created_at: "2026-04-18T10:00:00Z",
            updated_at: "2026-04-18T10:30:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 1,
          pending: 0,
          running: 0,
          completed: 1,
          failed: 0,
          cancelled: 0,
        },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("renders the dashboard shell and the legal review workload panel", () => {
    render(<DashboardPage />);

    expect(screen.getByTestId("dashboard-page-header")).toBeInTheDocument();
    expect(screen.getByTestId("setup-readiness-panel")).toHaveAttribute(
      "data-token",
      "tok",
    );
    expect(screen.getByTestId("setup-readiness-panel")).toHaveAttribute(
      "data-compact",
      "true",
    );
    expect(screen.getByTestId("dashboard-today-workbench")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Today workbench" }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-executive-decision-brief"),
    ).toBeInTheDocument();
    expect(screen.getByText("Executive decision brief")).toBeInTheDocument();
    expect(screen.getByText("Capacity runway")).toBeInTheDocument();
    expect(screen.getByText("85 left")).toBeInTheDocument();
    expect(
      screen.getByText("6 prepaid Report Credits included"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("running-pipelines-alert")).toBeInTheDocument();
    const aiDisclosure = screen.getByTestId("dashboard-ai-command-disclosure");
    expect(aiDisclosure).not.toHaveAttribute("open");
    expect(
      screen.getByText("Additional AI-assisted portfolio actions"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Expand for source-linked follow-ups beyond the executive next move.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("dashboard-ai-command-panel"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-setup-disclosure")).toHaveClass(
      "sm:overflow-visible",
      "sm:border-0",
    );
    expect(screen.getByTestId("dashboard-legal-review-disclosure")).toHaveClass(
      "sm:overflow-visible",
      "sm:border-0",
    );
    expect(screen.getByTestId("dashboard-risk-docket-disclosure")).toHaveClass(
      "sm:overflow-visible",
      "sm:border-0",
    );
    expect(screen.getByText("Workspace setup").closest("summary")).toHaveClass(
      "sm:hidden",
    );
    expect(
      screen.getByText("Legal review workload").closest("summary"),
    ).toHaveClass("sm:hidden");
    expect(
      screen.getByText("Risk & action docket").closest("summary"),
    ).toHaveClass("sm:hidden");
    expect(
      screen.getByTestId("legal-review-workload-panel"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("risk-activity-section")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-tooltip")).toBeInTheDocument();
  });

  it("renders the empty dashboard shell when there are no analyses", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 0,
          pending: 0,
          running: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
        },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<DashboardPage />);

    expect(screen.getByTestId("empty-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("setup-readiness-panel")).toBeInTheDocument();
    expect(screen.getByTestId("setup-readiness-panel")).toHaveAttribute(
      "data-compact",
      "false",
    );
    const hero = screen.getByTestId("empty-dashboard-hero");
    const readiness = screen.getByTestId("setup-readiness-panel");
    const featureProof = screen.getByTestId("empty-dashboard-feature-proof");
    expect(
      hero.compareDocumentPosition(readiness) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      readiness.compareDocumentPosition(featureProof) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.queryByTestId("legal-review-workload-panel"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("dashboard-ai-command-panel"),
    ).not.toBeInTheDocument();
  });

  it("does not flash the empty dashboard while auth token is pending", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    render(<DashboardPage />);

    expect(screen.queryByTestId("empty-dashboard")).not.toBeInTheDocument();
    expect(screen.getByTestId("dashboard-access-auth")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking dashboard access",
    );
  });

  it("hides cached dashboard metrics when the auth token disappears", () => {
    mockUseAuthToken.mockReturnValue(null);

    render(<DashboardPage />);

    expect(screen.getByTestId("dashboard-access-auth")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(
      screen.queryByTestId("dashboard-executive-decision-brief"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("dashboard-today-workbench"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("legal-review-workload-panel"),
    ).not.toBeInTheDocument();
  });

  it("hides cached dashboard metrics when access is restricted", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          {
            id: "ana-1",
            compound_input: "aspirin",
            compound_name: "Aspirin",
            compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
            status: "completed",
            current_step: 8,
            progress_pct: 100,
            overall_risk: "high",
            blocking_patents_count: 1,
            total_patents_found: 12,
            executive_summary: "Blocking exposure remains.",
            estimated_cost_usd: 4,
            pipeline_duration_seconds: 180,
            flagged_for_review: true,
            created_at: "2026-04-18T10:00:00Z",
            updated_at: "2026-04-18T10:30:00Z",
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: true,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });

    render(<DashboardPage />);

    expect(screen.getByTestId("dashboard-access-restricted")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Dashboard access restricted",
    );
    expect(
      screen.queryByTestId("dashboard-executive-decision-brief"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("dashboard-today-workbench"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("legal-review-workload-panel"),
    ).not.toBeInTheDocument();
  });

  it("hides cached billing capacity when billing access is restricted", () => {
    mockUseBillingStatus.mockReturnValue({
      data: {
        org_id: "org-1",
        plan: "pro",
        stripe_customer_id: "cus_1",
        stripe_subscription_id: "sub_1",
        subscription_status: "active",
        current_period_start: "2026-07-01T00:00:00.000Z",
        current_period_end: "2026-08-01T00:00:00.000Z",
        analyses_used: 21,
        analyses_limit: 106,
        included_analyses_limit: 100,
        purchased_credits_balance: 6,
        cancel_at_period_end: false,
      },
      error: new APIError(403, "Forbidden"),
      isLoading: false,
    });

    render(<DashboardPage />);

    expect(
      screen.getByTestId("dashboard-executive-decision-brief"),
    ).toBeInTheDocument();
    expect(screen.getByText("Capacity runway")).toBeInTheDocument();
    expect(screen.getByText("Restricted")).toBeInTheDocument();
    expect(
      screen.getByText("Billing capacity hidden until access is restored"),
    ).toBeInTheDocument();
    expect(screen.queryByText("85 left")).not.toBeInTheDocument();
    expect(
      screen.queryByText("6 prepaid Report Credits included"),
    ).not.toBeInTheDocument();
  });

  it("renders a trust-preserving recovery state when analyses cannot load", () => {
    const refetch = vi.fn();
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch,
    });

    render(<DashboardPage />);

    expect(
      screen.getByText("Dashboard temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Existing reports are not changed/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Keep dashboard metrics read-only/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
