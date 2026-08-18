import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewLaunchStep } from "@/components/analysis-wizard/review-launch-step";
import type { ConfigState } from "@/stores/config-store";
import type {
  MatterScopePreflightValue,
  ProductContextValue,
} from "@/types/pipeline";

vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ smiles }: { smiles: string }) => (
    <div data-testid="molecule-preview">{smiles}</div>
  ),
}));

function createConfig(overrides: Partial<ConfigState> = {}): ConfigState {
  return {
    trustMode: "explorer",
    jurisdictionBundle: "major_markets",
    targetJurisdictions: ["US", "EP", "UK", "IN", "JP", "CN"],
    searchMaxRankedResults: 200,
    searchTanimotoThreshold: 0.55,
    includeExpired: true,
    jurisdiction: "US",
    enablePubchem: true,
    enableBigquery: true,
    enableSurechembl: true,
    enablePatcid: true,
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    triageBatchSize: 10,
    citationTraversalEnabled: true,
    citationMaxDepth: 2,
    analysisThinkingBudget: 12000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO", "JP", "CN", "IN"],
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
  assetTypeHint: "small_molecule",
  developmentStage: "discovery",
  intendedActions: ["diligence_screen", "manufacture_import"],
};

const DEFAULT_LAUNCH_CAPACITY = {
  creditBackedRemaining: 6,
  includedRemaining: 79,
  isEnterprise: false,
  isLoading: false,
  purchasedCredits: 6,
  totalRemaining: 85,
};

const COMPLETE_HIGH_RELIANCE_CONTEXT: ProductContextValue = {
  productName: "PRV-142 oral tablet",
  dosageForm: "Film-coated tablet",
  routeOfAdministration: "Oral",
  strength: "200 mg",
  indication: "Pain",
  knownPatentsOrAssignees: ["US12345678", "Fictional Meridian"],
  commercialAction: "US launch diligence before term sheet",
  commercialTerritories: ["US"],
  manufacturingRoute: "Final API crystallized from ethanol",
  accusedActs: [
    {
      act: "manufacture",
      jurisdiction: "US",
      startDate: "2026-08-01",
      actor: "Praviar Therapeutics Ltd",
      status: "planned",
      purpose: "commercial",
      regulatoryPath: "none",
      instrumentality: "PRV-142 oral tablet",
      liabilityTheory: "direct",
    },
  ],
};

describe("ReviewLaunchStep", () => {
  it("presents a user-facing evidence plan rather than model internals", () => {
    render(
      <ReviewLaunchStep
        compoundInput="OC(=O)CCC(O)=O"
        inputType="SMILES"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        productContext={COMPLETE_HIGH_RELIANCE_CONTEXT}
        launchCapacity={DEFAULT_LAUNCH_CAPACITY}
        isLaunching={false}
        canLaunch
        launchError={null}
        onBack={vi.fn()}
        onLaunch={vi.fn()}
      />,
    );

    expect(screen.getByText("Evidence Plan")).toBeInTheDocument();
    expect(screen.getByText("Adaptive evidence execution")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Launch review brief" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Readiness contract")).toBeInTheDocument();
    const launchReviewBrief = screen.getByRole("region", {
      name: "Launch review brief",
    });
    expect(launchReviewBrief).toHaveTextContent("Matter identity");
    expect(launchReviewBrief).toHaveTextContent("OC(=O)CCC(O)=O");
    const launchBriefText = launchReviewBrief.textContent ?? "";
    expect(launchBriefText.indexOf("Matter identity")).toBeLessThan(
      launchBriefText.indexOf("Trust boundary"),
    );
    expect(launchBriefText.indexOf("Trust boundary")).toBeLessThan(
      launchBriefText.indexOf("Product context"),
    );
    expect(screen.getByText("Product context")).toBeInTheDocument();
    expect(screen.getByText("10 facts captured")).toBeInTheDocument();
    expect(screen.getByText("Product profile")).toBeInTheDocument();
    expect(screen.getAllByText("PRV-142 oral tablet").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Film-coated tablet").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("US12345678, Fictional Meridian").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "Small Molecule; Discovery; Diligence Screen, Manufacture Import confirmed for evidence routing.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence path")).toBeInTheDocument();
    expect(
      screen.getByText("4 sources selected; 7 search lanes"),
    ).toBeInTheDocument();
    expect(screen.getByText("Trust boundary")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The launch creates a first-pass FTO report request, not a legal clearance opinion.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Launch decision")).toBeInTheDocument();
    expect(screen.getByText("Ready to submit")).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Launch capacity and trust boundary",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Report Credit capacity")).toBeInTheDocument();
    expect(screen.getByText("85 Report Credits available")).toBeInTheDocument();
    expect(
      screen.getByText(
        "79 Report Credits included, 6 Report Credits credit-backed remaining, 6 Report Credits unused purchased. Included allowance is consumed first.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Launch boundary")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Start Analysis consumes launch capacity for a source-linked first-pass workflow/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Identifier status")).toBeInTheDocument();
    expect(
      screen.getByText(
        "SMILES syntax looks complete. Preview confirms rendering when available.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/agentic/i)).not.toBeInTheDocument();
    expect(screen.getByText("Evidence Scope")).toBeInTheDocument();
    expect(screen.getByText("Asset type")).toBeInTheDocument();
    expect(screen.getByText("Development stage")).toBeInTheDocument();
    expect(screen.getByText("Intended actions")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Calibrated internally from compound risk, source coverage, and confidence gates",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Review Gates")).toBeInTheDocument();
    expect(
      screen.getAllByText("Resolved identity approval before search").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Target lanes")).toBeInTheDocument();
    expect(screen.getByTestId("review-launch-source-card")).toHaveTextContent(
      "PubChem, BigQuery, SureChEMBL, PatCID",
    );
    expect(screen.getByText("Launch-ready lanes")).toBeInTheDocument();
    expect(screen.getByText("Staged lanes")).toBeInTheDocument();
    expect(screen.getByText("US, EP, IN, JP, CN")).toBeInTheDocument();
    expect(screen.getAllByText("UK").length).toBeGreaterThan(0);
    expect(screen.queryByText("Thinking Effort")).not.toBeInTheDocument();
    expect(screen.queryByText("Thinking Budget")).not.toBeInTheDocument();
    expect(screen.queryByText("Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("standard")).not.toBeInTheDocument();
    expect(screen.queryByText(/tokens/i)).not.toBeInTheDocument();
  });

  it("wraps long compound values and wires launch controls", () => {
    const onBack = vi.fn();
    const onLaunch = vi.fn();
    const longSmiles =
      "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O.CC(C)CC1=CC=C(C=C1)C(C)C(=O)O";

    render(
      <ReviewLaunchStep
        compoundInput={longSmiles}
        inputType="SMILES"
        config={createConfig({
          hitlEnabled: true,
          hitlCheckpoints: ["blocking_risk", "low_confidence"],
        })}
        matterScope={DEFAULT_MATTER_SCOPE}
        productContext={COMPLETE_HIGH_RELIANCE_CONTEXT}
        launchCapacity={DEFAULT_LAUNCH_CAPACITY}
        isLaunching={false}
        canLaunch
        launchError={null}
        onBack={onBack}
        onLaunch={onLaunch}
      />,
    );

    expect(
      screen
        .getAllByText(longSmiles)
        .some((element) => element.className.includes("break-all")),
    ).toBe(true);
    expect(
      screen.getAllByText(
        "Identity approval, then blocking risk, low confidence",
      ).length,
    ).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onLaunch).toHaveBeenCalledTimes(1);
  });

  it("keeps high-reliance scopes blocked until product context is explicit", () => {
    const onLaunch = vi.fn();

    render(
      <ReviewLaunchStep
        compoundInput="aspirin"
        inputType="Name"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        launchCapacity={DEFAULT_LAUNCH_CAPACITY}
        isLaunching={false}
        canLaunch
        launchError={null}
        onBack={vi.fn()}
        onLaunch={onLaunch}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "manufacture/import scopes require core product context before launch",
    );
    expect(screen.getByText("Launch blocked:")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Start Analysis" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    expect(onLaunch).not.toHaveBeenCalled();
  });

  it("surfaces secure-session, busy, and launch error states inline", () => {
    const { rerender } = render(
      <ReviewLaunchStep
        compoundInput="aspirin"
        inputType="Name"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        launchCapacity={{
          creditBackedRemaining: 0,
          includedRemaining: 0,
          isEnterprise: false,
          isLoading: false,
          purchasedCredits: 0,
          totalRemaining: 0,
        }}
        isLaunching={false}
        canLaunch={false}
        launchBlocker="Preparing secure session before launch controls are enabled."
        launchError={null}
        onBack={vi.fn()}
        onLaunch={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing secure session",
    );
    expect(screen.getByText("Action required")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Preparing secure session before launch controls are enabled.",
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Start Analysis" }),
    ).toBeDisabled();

    rerender(
      <ReviewLaunchStep
        compoundInput="aspirin"
        inputType="Name"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        launchCapacity={DEFAULT_LAUNCH_CAPACITY}
        isLaunching
        canLaunch
        launchError="Launch failed"
        onBack={vi.fn()}
        onLaunch={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Starting analysis and opening the evidence run."),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Launch failed");
  });

  it("shows restricted launch capacity without exposing stale credit counts", () => {
    const onLaunch = vi.fn();

    render(
      <ReviewLaunchStep
        compoundInput="aspirin"
        inputType="Name"
        config={createConfig()}
        matterScope={DEFAULT_MATTER_SCOPE}
        productContext={COMPLETE_HIGH_RELIANCE_CONTEXT}
        launchCapacity={{
          creditBackedRemaining: null,
          includedRemaining: null,
          isAccessRestricted: true,
          isEnterprise: false,
          isLoading: false,
          purchasedCredits: null,
          totalRemaining: null,
        }}
        isLaunching={false}
        canLaunch={false}
        launchBlocker="FTO report request capacity access is restricted. Restore billing access before starting another request."
        launchError={null}
        onBack={vi.fn()}
        onLaunch={onLaunch}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "FTO report request capacity access is restricted",
    );
    expect(screen.getByText("Access restricted")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Report Credit capacity is hidden until billing access is restored.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("85 Report Credits available"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Start Analysis" }));

    expect(onLaunch).not.toHaveBeenCalled();
  });
});
