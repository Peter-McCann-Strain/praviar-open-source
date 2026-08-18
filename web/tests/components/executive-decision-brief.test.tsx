import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ExecutiveDecisionBrief,
  buildDecisionMetrics,
  buildNextMove,
} from "@/components/dashboard/executive-decision-brief";
import type { BillingStatus } from "@/hooks/use-billing";
import type { AnalysisListItem } from "@/types/api";

const principalState = vi.hoisted(() => ({
  canViewBilling: true,
  canViewReviewQueue: true,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  canAccessWorkspaceHref: (_capabilities: unknown, href: string) =>
    href.startsWith("/billing")
      ? principalState.canViewBilling
      : href.startsWith("/reviews")
        ? principalState.canViewReviewQueue
        : true,
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: true,
      can_view_billing: principalState.canViewBilling,
      can_view_review_queue: principalState.canViewReviewQueue,
      role: "admin",
    },
  }),
}));

function analysisFixture(
  overrides: Partial<AnalysisListItem> = {},
): AnalysisListItem {
  return {
    id: "ana-1",
    compound_input: "aspirin",
    compound_name: "Aspirin",
    compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    status: "completed",
    current_step: 8,
    progress_pct: 100,
    overall_risk: "high",
    blocking_patents_count: 2,
    total_patents_found: 42,
    executive_summary: "Blocking composition claims remain active.",
    estimated_cost_usd: 10,
    pipeline_duration_seconds: 180,
    flagged_for_review: false,
    created_at: "2026-06-18T10:00:00Z",
    updated_at: "2026-06-18T10:30:00Z",
    ...overrides,
  };
}

function billingFixture(overrides: Partial<BillingStatus> = {}): BillingStatus {
  return {
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
    purchased_credits_used: 0,
    cancel_at_period_end: false,
    ...overrides,
  };
}

describe("ExecutiveDecisionBrief", () => {
  beforeEach(() => {
    principalState.canViewBilling = true;
    principalState.canViewReviewQueue = true;
  });

  it("builds executive review metrics from analysis and billing state", () => {
    const metrics = buildDecisionMetrics({
      analyses: [
        analysisFixture({ id: "blocked", blocking_patents_count: 3 }),
        analysisFixture({
          id: "clear",
          overall_risk: "clear",
          blocking_patents_count: 0,
        }),
        analysisFixture({
          id: "review",
          overall_risk: "medium",
          blocking_patents_count: 0,
          review_status: {
            is_persisted: true,
            status: "changes_requested",
          },
        }),
      ],
      billingStatus: billingFixture({ analyses_limit: 10, analyses_used: 9 }),
    });

    expect(metrics.map((metric) => [metric.label, metric.value])).toEqual([
      ["Blocked assets", "1"],
      ["Clear to progress", "1"],
      ["Counsel bottleneck", "2"],
      ["Capacity runway", "1 left"],
    ]);
    expect(metrics[2]?.href).toBe("/reviews?filter=escalated&sort=priority");
    expect(metrics[3]?.tone).toBe("warning");
  });

  it("masks billing capacity metrics when billing access is restricted", () => {
    const metrics = buildDecisionMetrics({
      analyses: [analysisFixture()],
      billingStatus: billingFixture({ analyses_limit: 106, analyses_used: 21 }),
      isBillingAccessRestricted: true,
    });

    expect(metrics[3]).toMatchObject({
      detail: "Billing capacity hidden until access is restored",
      href: "/billing",
      label: "Capacity runway",
      tone: "warning",
      value: "Restricted",
    });
  });

  it("shows only purchased runway after a lapsed allowance downgrade", () => {
    const metrics = buildDecisionMetrics({
      analyses: [analysisFixture()],
      billingStatus: billingFixture({
        subscription_status: "past_due",
        analyses_used: 5,
        analyses_limit: 7,
        included_analyses_limit: 3,
        purchased_credits_balance: 2,
        purchased_credits_used: 0,
      }),
    });

    expect(metrics[3]).toMatchObject({
      detail: "2 prepaid Report Credits included",
      label: "Capacity runway",
      tone: "warning",
      value: "2 left",
    });
  });

  it("replaces hidden risk metrics with a counsel-only posture", () => {
    const metrics = buildDecisionMetrics({
      analyses: [
        analysisFixture({
          overall_risk: null,
          blocking_patents_count: null,
          risk_ratings_restricted: true,
        }),
      ],
      billingStatus: billingFixture(),
    });

    expect(metrics[0]).toMatchObject({
      detail: expect.stringContaining("no zero-risk conclusion is inferred"),
      href: "/analyses",
      label: "Risk posture",
      value: "Counsel only",
    });
    expect(metrics.map((metric) => metric.label)).not.toContain(
      "Blocked assets",
    );
    expect(metrics.map((metric) => metric.label)).not.toContain(
      "Clear to progress",
    );
  });

  it("prioritizes the highest-risk AI next move", () => {
    expect(
      buildNextMove([
        analysisFixture({
          id: "blocked",
          compound_name: "Succinic acid",
          blocking_patents_count: 3,
        }),
        analysisFixture({
          id: "running",
          compound_name: "Ibuprofen",
          status: "running",
          overall_risk: null,
          blocking_patents_count: 0,
        }),
      ]),
    ).toMatchObject({
      cta: "Open blocker brief",
      href: "/analyses/blocked/report?ai_context=blocker_brief&tab=patents",
      label: "Draft blocking-patent brief",
    });
  });

  it("renders executive posture, trust controls, and navigable decision cells", () => {
    render(
      <ExecutiveDecisionBrief
        analyses={[
          analysisFixture({
            id: "blocked",
            compound_name: "Succinic acid",
            blocking_patents_count: 3,
          }),
          analysisFixture({
            id: "clear",
            compound_name: "Ibuprofen",
            overall_risk: "clear",
            blocking_patents_count: 0,
          }),
        ]}
        billingStatus={billingFixture({
          analyses_limit: 106,
          analyses_used: 21,
          purchased_credits_balance: 6,
        })}
        sampleWindowSize={2}
        totalAnalyses={145}
      />,
    );

    const brief = screen.getByTestId("dashboard-executive-decision-brief");
    expect(
      within(brief).getByRole("heading", {
        name: "Portfolio calls ready for leadership",
      }),
    ).toBeInTheDocument();
    expect(
      within(brief).getByText("Latest 2 of 145 analyses"),
    ).toBeInTheDocument();
    expect(within(brief).getByText("Blocked assets")).toBeInTheDocument();
    expect(within(brief).getByText("Clear to progress")).toBeInTheDocument();
    expect(within(brief).getByText("Counsel bottleneck")).toBeInTheDocument();
    expect(within(brief).getByText("Capacity runway")).toBeInTheDocument();
    expect(within(brief).getByText("85 left")).toBeInTheDocument();
    expect(
      within(brief).getByText("6 prepaid Report Credits included"),
    ).toBeInTheDocument();
    expect(within(brief).getByText("AI next move")).toBeInTheDocument();
    expect(within(brief).getByText("Source-linked")).toBeInTheDocument();
    expect(within(brief).getByText("Human review gate")).toBeInTheDocument();
    expect(
      within(brief).getByText("Calibrated to current evidence"),
    ).toBeInTheDocument();
    expect(
      within(brief).getByRole("link", { name: /Open blocker brief/i }),
    ).toHaveClass("min-h-11");
    expect(
      within(brief).getByRole("link", { name: /Open blocker brief/i }),
    ).toHaveAttribute(
      "href",
      "/analyses/blocked/report?ai_context=blocker_brief&tab=patents",
    );
    expect(
      within(brief).getByRole("link", { name: /Capacity runway/i }),
    ).toHaveAttribute("href", "/billing?intent=credits");
    expect(
      within(brief).getByRole("link", { name: /Counsel bottleneck/i }),
    ).toHaveAttribute("href", "/reviews?filter=escalated&sort=priority");
  });

  it("uses a three-column executive grid when exactly three metrics are visible", () => {
    principalState.canViewBilling = false;

    render(
      <ExecutiveDecisionBrief
        analyses={[analysisFixture()]}
        billingStatus={billingFixture()}
        sampleWindowSize={1}
        totalAnalyses={1}
      />,
    );

    const blockedMetric = screen.getByRole("link", {
      name: /Blocked assets/i,
    });
    expect(blockedMetric.parentElement).toHaveClass("2xl:grid-cols-3");
    expect(blockedMetric.parentElement).not.toHaveClass("2xl:grid-cols-4");
  });
});
