import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EvidenceLaunchRail } from "@/components/analysis-wizard/evidence-launch-rail";
import type { ConfigState } from "@/stores/config-store";
import type { MatterScopePreflightValue } from "@/types/pipeline";

function createConfig(overrides: Partial<ConfigState> = {}): ConfigState {
  return {
    trustMode: "counsel",
    jurisdictionBundle: "major_markets",
    targetJurisdictions: ["US", "EP", "UK", "IN", "JP", "CN"],
    searchMaxRankedResults: 200,
    searchTanimotoThreshold: 0.55,
    includeExpired: true,
    jurisdiction: "US",
    enablePubchem: true,
    enableBigquery: true,
    enableSurechembl: false,
    enablePatcid: true,
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    triageBatchSize: 10,
    citationTraversalEnabled: true,
    citationMaxDepth: 2,
    analysisThinkingBudget: 12000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO"],
    thinkingEffortAnalysis: "high",
    thinkingEffortTriage: "medium",
    thinkingEffortReport: "high",
    hitlEnabled: false,
    hitlCheckpoints: [],
    hitlAutoSkipMinutes: 10,
    setConfig: vi.fn(),
    applyJurisdictionBundle: vi.fn(),
    setTargetJurisdictions: vi.fn(),
    toggleTargetJurisdiction: vi.fn(),
    applyPreset: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  };
}

const DEFAULT_MATTER_SCOPE: MatterScopePreflightValue = {
  assetTypeHint: "formulation",
  developmentStage: "clinical",
  intendedActions: ["formulation_review", "commercial_launch"],
};

describe("EvidenceLaunchRail", () => {
  it("renders persistent launch context with official workflow stages", () => {
    const { container } = render(
      <EvidenceLaunchRail
        compoundInput="OC(=O)CCC(O)=O"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        step={2}
      />,
    );

    expect(
      screen.getByRole("complementary", { name: /evidence launch readiness/i }),
    ).toBeInTheDocument();
    const disclosure = screen.getByTestId("evidence-launch-mobile-disclosure");
    expect(disclosure).toHaveClass("sm:contents");
    expect(screen.getByText(/Run readiness · \d+\/\d+/i)).toBeVisible();
    expect(screen.getByText("OC(=O)CCC(O)=O")).toBeInTheDocument();
    expect(
      screen.getAllByText("PubChem, BigQuery, PatCID").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("US, EP, UK, IN, JP, CN, WO").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Source search")).toBeInTheDocument();
    expect(screen.getByText("Adaptive triage")).toBeInTheDocument();
    expect(screen.getByText("Claim packet")).toBeInTheDocument();
    expect(screen.getByText("Counsel handoff")).toBeInTheDocument();
    expect(screen.getAllByText("Scope").length).toBeGreaterThan(0);
    expect(screen.getByText("Handoff path")).toBeInTheDocument();
    expect(screen.getByText("Current: Adaptive triage")).toBeInTheDocument();
    expect(
      screen.getByText("Adaptive triage").closest("[aria-current='step']"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI launch brief" }),
    ).toHaveAttribute("data-testid", "launch-copilot-brief");
    expect(screen.getByText("AI launch brief")).toBeInTheDocument();
    expect(screen.getByText("Wait for launch capacity")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Keep configuring while Praviar confirms the latest report request capacity.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Quota is enforced before analysis starts").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("prepared")).toBeInTheDocument();
    expect(screen.getAllByText("pending").length).toBeGreaterThan(0);
    expect(
      container.querySelector(".praviar-evidence-field-pattern"),
    ).toBeTruthy();
    expect(container.querySelector("[data-praviar-mark-frame]")).toBeTruthy();
    expect(container.querySelector(".praviar-chart-swatch")).toBeTruthy();
    expect(
      screen.getByLabelText(/Compound: Ready; SMILES; ready/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        /Scope: Formulation; Clinical; 2 actions confirmed for evidence routing; ready/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Matter scope")).toBeInTheDocument();
    expect(screen.getAllByText("Formulation; Clinical").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText("Formulation Review, Commercial Launch"),
    ).toBeInTheDocument();
  });

  it("keeps repeated launch details inside progressive disclosure controls", () => {
    render(
      <EvidenceLaunchRail
        compoundInput="aspirin"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        step={1}
      />,
    );

    const packetDetails = screen
      .getAllByText("Scope")
      .find((element) => element.closest("summary"))
      ?.closest("details");
    const executionPath = screen.getByText("Handoff path").closest("details");

    expect(packetDetails).toBeInTheDocument();
    expect(packetDetails).not.toHaveAttribute("open");
    expect(executionPath).toBeInTheDocument();
    expect(executionPath).not.toHaveAttribute("open");
    expect(
      screen.getByText(/aspirin · PubChem, BigQuery, PatCID/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Current: Source search")).toBeInTheDocument();
  });

  it("shows an awaiting state before a compound is provided", () => {
    render(
      <EvidenceLaunchRail
        compoundInput=""
        config={createConfig({
          jurisdictionBundle: "custom",
          searchJurisdictions: ["JP"],
          targetJurisdictions: ["JP"],
        })}
        step={1}
      />,
    );

    expect(screen.getByText("Awaiting input")).toBeInTheDocument();
    expect(screen.getByText("Add the compound identifier")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Enter a compound name, SMILES, InChI, InChIKey, CAS number, or internal project code.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("Compound readiness is the open launch check."),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Name, SMILES, InChI, InChIKey, or CAS")[0],
    ).toBeInTheDocument();
    expect(screen.getAllByText("JP, WO").length).toBeGreaterThan(0);
  });

  it("does not mark malformed compound identifiers as ready in the launch rail", () => {
    render(
      <EvidenceLaunchRail
        compoundInput="110-15-7"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        step={1}
      />,
    );

    expect(
      screen.getByLabelText(
        /Compound: Needs review; The CAS checksum does not match/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/Compound: Ready; CAS Number; ready/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Review the compound identifier"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "The CAS checksum does not match. Check the digits before using a Report Credit.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("surfaces disabled sources and depleted launch capacity as attention states", () => {
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "starter",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 25,
          analyses_limit: 25,
          included_analyses_limit: 25,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        canManageBilling
        compoundInput="aspirin"
        config={createConfig({
          enablePubchem: false,
          enableBigquery: false,
          enableSurechembl: false,
          enablePatcid: false,
        })}
        step={2}
      />,
    );

    expect(screen.getByText("Run readiness")).toBeInTheDocument();
    expect(screen.getByText("No sources")).toBeInTheDocument();
    expect(
      screen.getAllByText("Enable at least one patent source").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("0 report requests available")).toBeInTheDocument();
    expect(
      screen.getByText(
        "0 included, 0 credit-backed remaining; 0 unused purchased",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "1 Report Credit = 1 first-pass FTO report request for 1 compound",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Report Credits required before launch"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Buy 1 Report Credit to launch this first-pass FTO report without changing subscription tier. Larger packs remain available on the billing page.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Start Analysis remains disabled until report-request capacity is available.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Capacity is checked against included allowance plus purchased Report Credits.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Resolve report capacity"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Launch capacity recovery" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("launch-copilot-brief")).toContainElement(
      screen.getByTestId("capacity-credit-action"),
    );
    const buyCreditLink = screen.getByRole("link", {
      name: /Buy 1 Report Credit/i,
    });
    expect(buyCreditLink).toHaveClass("min-h-11", "w-full");
    expect(buyCreditLink).toHaveAttribute(
      "href",
      "/billing?intent=credits&needed_reports=1&pack=single_analysis&return_to=%2Fanalyses%2Fnew%3Fresume%3Dcredit_checkout&source=launch",
    );
  });

  it("routes tight launch capacity to credit pack review without blocking ready state", () => {
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "pro",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 96,
          analyses_limit: 100,
          included_analyses_limit: 100,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        canManageBilling
        compoundInput="aspirin"
        config={createConfig()}
        step={2}
      />,
    );

    expect(screen.getByText("4 report requests available")).toBeInTheDocument();
    expect(screen.getByText("4 report requests available")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Capacity is tight")).toBeInTheDocument();
    expect(screen.getByText("Capacity watch")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Start Analysis remains available, but the next diligence run may require more capacity.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Protect launch runway")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Review Report Credit Packs/i }),
    ).toHaveAttribute(
      "href",
      "/billing?intent=credits&needed_reports=1&pack=portfolio_5&return_to=%2Fanalyses%2Fnew%3Fresume%3Dcredit_checkout&source=launch",
    );
  });

  it("sends depleted non-admin capacity through the in-app admin request", () => {
    const onRequestReportCredits = vi.fn();
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "starter",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 25,
          analyses_limit: 25,
          included_analyses_limit: 25,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        compoundInput="aspirin"
        config={createConfig()}
        onRequestReportCredits={onRequestReportCredits}
        step={2}
      />,
    );

    expect(
      screen.getByText("Workspace admin action required"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Request Report Credits" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Request Report Credits" }),
    );
    expect(onRequestReportCredits).toHaveBeenCalledWith(1, "analysis_launch");
  });

  it("notifies admins in-app when non-admin launch capacity is tight", () => {
    const onRequestReportCredits = vi.fn();
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "pro",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 96,
          analyses_limit: 100,
          included_analyses_limit: 100,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        compoundInput="aspirin"
        config={createConfig()}
        onRequestReportCredits={onRequestReportCredits}
        step={2}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Notify workspace admin" }),
    );
    expect(onRequestReportCredits).toHaveBeenCalledWith(5, "capacity_watch");
  });

  it("masks stale launch capacity and credit actions when billing access is restricted", () => {
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "pro",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 96,
          analyses_limit: 100,
          included_analyses_limit: 100,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        compoundInput="aspirin"
        config={createConfig()}
        isBillingAccessRestricted
        step={2}
      />,
    );

    expect(screen.getByText("Access restricted")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Report Credit capacity hidden until access is restored",
      ).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Restore billing access")).toBeInTheDocument();
    expect(
      screen.queryByText("4 report requests available"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Review Report Credit Packs/i }),
    ).not.toBeInTheDocument();
  });

  it("uses effective capacity when purchased Report Credits have already been consumed", () => {
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "starter",
          stripe_customer_id: "cus_1",
          stripe_subscription_id: "sub_1",
          subscription_status: "active",
          current_period_start: "2026-06-01T00:00:00.000Z",
          current_period_end: "2026-07-01T00:00:00.000Z",
          analyses_used: 30,
          analyses_limit: 32,
          included_analyses_limit: 25,
          purchased_credits_balance: 1,
          cancel_at_period_end: false,
        }}
        compoundInput="aspirin"
        config={createConfig()}
        step={2}
      />,
    );

    expect(screen.getByText("2 report requests available")).toBeInTheDocument();
    expect(
      screen.getByText(
        "0 included, 1 credit-backed remaining, 1 additional workspace report request; 1 unused purchased",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Capacity is tight")).toBeInTheDocument();
    expect(
      screen.queryByText("Report Credits required before launch"),
    ).not.toBeInTheDocument();
  });

  it("omits empty compound context from launch credit checkout return URLs", () => {
    render(
      <EvidenceLaunchRail
        billingStatus={{
          org_id: "org_1",
          plan: "free",
          stripe_customer_id: null,
          stripe_subscription_id: null,
          subscription_status: null,
          current_period_start: null,
          current_period_end: null,
          analyses_used: 0,
          analyses_limit: 0,
          included_analyses_limit: 0,
          purchased_credits_balance: 0,
          cancel_at_period_end: false,
        }}
        canManageBilling
        compoundInput="   "
        config={createConfig({ patentSources: [] })}
        step={2}
      />,
    );

    expect(
      screen.getByRole("link", { name: /Buy 1 Report Credit/i }),
    ).toHaveAttribute(
      "href",
      "/billing?intent=credits&needed_reports=1&pack=single_analysis&return_to=%2Fanalyses%2Fnew%3Fresume%3Dcredit_checkout&source=launch",
    );
  });

  it("keeps long compound identifiers inspectable in the launch rail", () => {
    const longIdentifier = `InChI=1S/${"C".repeat(120)}-patent-scope`;

    render(
      <EvidenceLaunchRail
        compoundInput={longIdentifier}
        config={createConfig()}
        step={1}
      />,
    );

    const compound = screen.getByText(longIdentifier);

    expect(compound).toHaveAttribute("title", longIdentifier);
    expect(compound).toHaveClass("[overflow-wrap:anywhere]");
  });
});
