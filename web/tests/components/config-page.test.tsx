import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import ConfigPage from "@/app/(dashboard)/config/page";
import { AnalysisScopeSection } from "@/components/config/analysis-scope-section";
import { ConfigEditPanel } from "@/components/config/config-edit-panel";
import { ConfigPresetGrid } from "@/components/config/config-preset-grid";
import { ConfigReadOnlySummaryCard } from "@/components/config/config-read-only-summary-card";
import { ConfigStatusStrip } from "@/components/config/config-workspace-status";
import {
  getConfigValidationIssues,
  getCoverageBudgetLabel,
  PATENT_SOURCES,
} from "@/components/config/helpers";
import { HitlSection } from "@/components/config/hitl-section";
import { JurisdictionsThinkingSection } from "@/components/config/jurisdictions-thinking-section";
import { PatentSourcesSection } from "@/components/config/patent-sources-section";
import { SearchDepthSection } from "@/components/config/search-depth-section";
import { useConfigStore, type ConfigState } from "@/stores/config-store";
import { APIError } from "@/lib/api-client";

const mocks = vi.hoisted(() => ({
  addToast: vi.fn(),
  apiClient: vi.fn(),
  useAuthToken: vi.fn(),
  useOrgDefaultConfig: vi.fn(),
  configAuth: {
    hasClerk: false,
    isLoaded: true,
    orgRole: "org:admin" as string | null,
  },
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    isLoaded: mocks.configAuth.isLoaded,
    orgRole: mocks.configAuth.orgRole,
  }),
}));

vi.mock("@/components/layout/sidebar-constants", () => ({
  get hasClerk() {
    return mocks.configAuth.hasClerk;
  },
  isAdminOrgRole: (orgRole: string | null | undefined) =>
    orgRole === "org:admin" || orgRole === "admin",
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    hydratedAuthScope: null,
    ...actual,
    apiClient: mocks.apiClient,
  };
});

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mocks.useAuthToken(),
}));

vi.mock("@/hooks/use-config", () => ({
  useOrgDefaultConfig: (token: string | null) =>
    mocks.useOrgDefaultConfig(token),
}));

vi.mock("@/stores/toast-store", () => ({
  useToastStore: () => ({ addToast: mocks.addToast }),
}));

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
    enableSurechembl: true,
    enablePatcid: true,
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    triageBatchSize: 10,
    citationTraversalEnabled: true,
    citationMaxDepth: 2,
    analysisThinkingBudget: 12000,
    expiredGraceYears: 5,
    searchJurisdictions: ["US", "EP", "WO", "JP", "KR", "CN"],
    thinkingEffortAnalysis: "high",
    thinkingEffortTriage: "medium",
    thinkingEffortReport: "high",
    hitlEnabled: false,
    hitlCheckpoints: [
      "search_review",
      "triage_review",
      "analysis_review",
      "report_review",
    ],
    hitlAutoSkipMinutes: 10,
    setConfig: vi.fn(),
    hydrateConfig: vi.fn(),
    applyJurisdictionBundle: vi.fn(),
    setTargetJurisdictions: vi.fn(),
    toggleTargetJurisdiction: vi.fn(),
    applyPreset: vi.fn(),
    reset: vi.fn(),
    clearAuthScope: vi.fn(),
    ...overrides,
  };
}

describe("configuration workspace helpers", () => {
  it("keeps custom coverage budgets distinct from balanced coverage", () => {
    expect(getCoverageBudgetLabel(100)).toBe("Custom coverage");
    expect(getCoverageBudgetLabel(200)).toBe("Balanced coverage");
  });

  it("reports save-blocking invalid defaults", () => {
    const config = createConfig({
      enablePubchem: false,
      enableBigquery: false,
      enableSurechembl: false,
      enablePatcid: false,
      searchJurisdictions: [],
      hitlEnabled: true,
      hitlCheckpoints: [],
    });

    expect(getConfigValidationIssues(config)).toEqual([
      "Enable at least one patent source.",
      "Select at least one search jurisdiction.",
      "Select at least one HITL checkpoint or turn HITL off.",
    ]);
  });

  it("blocks configurations with no launch-ready jurisdiction lanes", () => {
    const config = createConfig({
      jurisdictionBundle: "custom",
      targetJurisdictions: ["UK"],
      searchJurisdictions: ["UK", "WO"],
    });

    expect(getConfigValidationIssues(config)).toEqual([
      "Select at least one launch-ready jurisdiction: US, EP, IN, JP, or CN.",
    ]);
  });
});

describe("configuration workspace components", () => {
  it("exposes selected coverage profile state accessibly", () => {
    const config = createConfig();

    render(<ConfigPresetGrid config={config} />);

    expect(
      screen.getByRole("button", { name: /balanced coverage profile/i }),
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(
      screen.getByRole("button", { name: /expanded coverage profile/i }),
    );

    expect(config.applyPreset).toHaveBeenCalledWith("thorough");
  });

  it("shows exact custom budget and explicit empty summary states", () => {
    const config = createConfig({
      searchMaxRankedResults: 100,
      searchJurisdictions: [],
    });

    render(
      <ConfigReadOnlySummaryCard
        config={config}
        enabledSources={[]}
        onEdit={vi.fn()}
      />,
    );

    expect(screen.getByText("Custom coverage")).toBeInTheDocument();
    expect(
      screen.getByText("100 ranked results passed through scoring"),
    ).toBeInTheDocument();
    expect(screen.getByText("No patent sources enabled")).toBeInTheDocument();
    expect(
      screen.getAllByText("No jurisdictions selected").length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /edit defaults/i })).toHaveClass(
      "min-h-11",
    );
  });

  it("removes the stale single-jurisdiction control from search coverage", () => {
    render(<SearchDepthSection config={createConfig()} />);

    expect(screen.queryByLabelText(/^Jurisdiction$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ranked Result Budget")).toHaveClass(
      "h-11",
      "focus-visible:ring-2",
    );
    expect(screen.getByLabelText("Tanimoto Threshold")).toHaveClass("h-11");
    expect(
      screen.getByLabelText("Include Expired Patents").closest("label"),
    ).toHaveClass("min-h-11", "min-w-11");
  });

  it("uses touch-safe selects in evidence review limits", () => {
    render(<AnalysisScopeSection config={createConfig()} />);

    fireEvent.click(
      screen.getByRole("button", { name: /evidence review limits/i }),
    );

    expect(screen.getByLabelText("Patent Review Limit")).toHaveClass("h-11");
    expect(screen.getByLabelText("DoE Candidate Limit")).toHaveClass("h-11");
    expect(screen.getByLabelText("Triage Batch Size")).toHaveClass("h-11");
  });

  it("keeps draft-mode actions touch-safe", () => {
    render(<ConfigEditPanel config={createConfig()} onCollapse={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: /return to summary/i }),
    ).toHaveClass("min-h-11");
  });

  it("prevents removing the final active patent source", () => {
    render(
      <PatentSourcesSection
        config={createConfig({
          enablePubchem: true,
          enableBigquery: false,
          enableSurechembl: false,
          enablePatcid: false,
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /patent sources/i }));

    expect(screen.getByLabelText(/PubChem SDQ/i)).toBeDisabled();
    expect(screen.getByLabelText(/PubChem SDQ/i).closest("label")).toHaveClass(
      "min-h-[5.5rem]",
      "focus-within:ring-2",
    );
    expect(screen.getByText("Last active source")).toBeInTheDocument();
  });

  it("labels HITL controls and prevents removing the final checkpoint", () => {
    render(
      <HitlSection
        config={createConfig({
          hitlEnabled: true,
          hitlCheckpoints: ["search_review"],
        })}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /human-in-the-loop checkpoints/i,
      }),
    );

    expect(
      screen.getByText("Resolved identity approval is always required"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Enable additional review checkpoints"),
    ).toBeChecked();
    expect(
      screen
        .getByLabelText("Enable additional review checkpoints")
        .closest("label"),
    ).toHaveClass("min-h-11", "min-w-11");
    expect(screen.getByLabelText("Auto-skip Timeout")).toHaveClass("h-11");
    expect(screen.getByLabelText(/After Search/i)).toBeDisabled();
    expect(screen.getByLabelText(/After Search/i).closest("label")).toHaveClass(
      "min-h-11",
      "focus-within:ring-2",
    );
  });

  it("labels execution-rigor selects by stage", () => {
    render(<JurisdictionsThinkingSection config={createConfig()} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /jurisdictions & execution rigor/i,
      }),
    );

    expect(screen.getByLabelText("Analysis")).toHaveClass("h-11");
    expect(screen.getByLabelText("Triage")).toHaveClass("h-11");
    expect(screen.getByLabelText("Report")).toHaveClass("h-11");
    expect(
      screen.getByLabelText("Select United States (US)").closest("label"),
    ).toHaveClass("min-h-11", "focus-within:ring-2");
  });

  it("derives the source status total from the patent source registry", () => {
    const config = createConfig();

    render(
      <ConfigStatusStrip
        config={config}
        enabledSources={PATENT_SOURCES.map((source) => source.label)}
        validationIssues={[]}
        authenticated
        saving={false}
        editing={false}
        resetPending={false}
        defaultsLoading={false}
        defaultsUnavailable={false}
      />,
    );

    expect(
      screen.getByText(
        `${PATENT_SOURCES.length} of ${PATENT_SOURCES.length} enabled`,
      ),
    ).toBeInTheDocument();
  });

  it("uses one authoritative policy posture for valid defaults", () => {
    const config = createConfig();

    const { container } = render(
      <ConfigStatusStrip
        config={config}
        enabledSources={PATENT_SOURCES.map((source) => source.label)}
        validationIssues={[]}
        authenticated
        saving={false}
        editing
        resetPending={false}
        defaultsLoading={false}
        defaultsUnavailable={false}
      />,
    );

    const status = screen.getByRole("status");
    expect(
      screen.getByRole("heading", { name: /policy posture/i }),
    ).toBeInTheDocument();
    expect(status).toHaveTextContent("Ready to save");
    expect(
      container.querySelector("[data-config-policy-posture]"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Save readiness")).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        /Required sources, jurisdictions, and review checkpoints/i,
      ),
    ).not.toBeInTheDocument();
  });

  it("does not claim review checkpoints are configured when HITL is off", () => {
    render(
      <ConfigStatusStrip
        config={createConfig({ hitlEnabled: false, hitlCheckpoints: [] })}
        enabledSources={PATENT_SOURCES.map((source) => source.label)}
        validationIssues={[]}
        authenticated
        saving={false}
        editing={false}
        resetPending={false}
        defaultsLoading={false}
        defaultsUnavailable={false}
      />,
    );

    expect(screen.getByText("No review pauses")).toBeInTheDocument();
    expect(
      screen.queryByText(/review checkpoints are configured/i),
    ).not.toBeInTheDocument();
  });

  it("announces loading defaults instead of stale ready copy", () => {
    render(
      <ConfigStatusStrip
        config={createConfig()}
        enabledSources={PATENT_SOURCES.map((source) => source.label)}
        validationIssues={[]}
        authenticated
        saving={false}
        editing={false}
        resetPending={false}
        defaultsLoading
        defaultsUnavailable={false}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading organization defaults",
    );
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
  });

  it("keeps review-gate status separate from source blockers", () => {
    render(
      <ConfigStatusStrip
        config={createConfig({ enablePubchem: false })}
        enabledSources={[]}
        validationIssues={["Enable at least one patent source."]}
        authenticated
        saving={false}
        editing={false}
        resetPending={false}
        defaultsLoading={false}
        defaultsUnavailable={false}
      />,
    );

    expect(screen.getByText("No review pauses")).toBeInTheDocument();
    expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
  });

  it("does not announce save readiness without an authorized session", () => {
    render(
      <ConfigStatusStrip
        config={createConfig()}
        enabledSources={PATENT_SOURCES.map((source) => source.label)}
        validationIssues={[]}
        authenticated={false}
        saving={false}
        editing={false}
        resetPending={false}
        defaultsLoading={false}
        defaultsUnavailable={false}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Sign in required");
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
  });
});

describe("ConfigPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useAuthToken.mockReturnValue("token");
    mocks.configAuth.hasClerk = false;
    mocks.configAuth.isLoaded = true;
    mocks.configAuth.orgRole = "org:admin";
    mocks.apiClient.mockResolvedValue({});
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: { config: {}, can_manage: true },
      isLoading: false,
      isError: false,
    });
    useConfigStore.getState().reset();
  });

  it("blocks invalid defaults with visible readiness feedback", () => {
    act(() => {
      useConfigStore.getState().setConfig({
        enablePubchem: false,
        enableBigquery: false,
        enableSurechembl: false,
        enablePatcid: false,
      });
    });

    render(<ConfigPage />);

    const header = screen.getByTestId("config-app-surface-header");

    expect(header).toBeInTheDocument();
    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "compact",
    );
    expect(header).toHaveClass("px-3", "py-4", "sm:px-6");
    expect(screen.getByRole("heading", { name: "Configuration" })).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Review required");
    const saveDefaultsButton = screen.getByRole("button", {
      name: /save defaults/i,
    });
    expect(saveDefaultsButton).toHaveClass(
      "min-h-11",
      "min-w-0",
      "px-2",
      "sm:px-4",
    );
    expect(saveDefaultsButton.parentElement?.parentElement).toHaveClass(
      "min-w-0",
    );
    expect(
      screen.getByRole("button", {
        name: /prepare to reset configuration defaults/i,
      }),
    ).toHaveClass("min-h-11", "min-w-0", "px-2", "sm:px-4");
    expect(saveDefaultsButton).toBeDisabled();
    expect(saveDefaultsButton).toHaveAccessibleDescription(
      /Enable at least one patent source/i,
    );
    expect(
      screen.getByText("Enable at least one patent source."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: /governance/i }),
    ).toBeInTheDocument();
  });

  it("gives members a clear read-only policy view with no mutation controls", () => {
    mocks.configAuth.hasClerk = true;
    mocks.configAuth.orgRole = "org:member";
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: { config: {}, can_manage: false },
      isLoading: false,
      isError: false,
    });

    render(<ConfigPage />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Read-only organization defaults",
    );
    expect(
      screen.getAllByText(
        /An attorney or organization administrator can draft, reset, or save defaults/i,
      ).length,
    ).toBeGreaterThanOrEqual(3);
    expect(
      screen.getByText("Current Organization Defaults"),
    ).toBeInTheDocument();
    expect(screen.getByText("Read-only policy view")).toBeInTheDocument();
    expect(
      screen.queryByText("Default Policy Profiles"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /edit defaults/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save defaults/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /reset configuration defaults/i }),
    ).not.toBeInTheDocument();
    expect(mocks.apiClient).not.toHaveBeenCalled();
  });

  it("uses the API capability so attorney policy managers are not hidden by Clerk organization roles", () => {
    mocks.configAuth.hasClerk = true;
    mocks.configAuth.orgRole = "org:member";
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: { config: {}, can_manage: true },
      isLoading: false,
      isError: false,
    });

    render(<ConfigPage />);

    expect(
      screen.getByRole("button", { name: /save defaults/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Default Policy Profiles")).toBeInTheDocument();
    expect(screen.queryByText("Read-only policy view")).not.toBeInTheDocument();
  });

  it("withholds policy data and actions until the Clerk role is loaded", () => {
    mocks.configAuth.hasClerk = true;
    mocks.configAuth.isLoaded = false;
    mocks.configAuth.orgRole = null;

    render(<ConfigPage />);

    expect(
      screen.getByText("Checking configuration access"),
    ).toBeInTheDocument();
    expect(screen.getByText("No policy values exposed")).toBeInTheDocument();
    expect(
      screen.queryByText("Current Organization Defaults"),
    ).not.toBeInTheDocument();
    expect(mocks.useOrgDefaultConfig).not.toHaveBeenCalled();
    expect(mocks.apiClient).not.toHaveBeenCalled();
  });

  it("requires reset confirmation before mutating local defaults", () => {
    act(() => {
      useConfigStore.getState().setConfig({ searchMaxRankedResults: 500 });
    });

    render(<ConfigPage />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /prepare to reset configuration defaults/i,
      }),
    );

    expect(useConfigStore.getState().searchMaxRankedResults).toBe(500);
    expect(mocks.addToast).toHaveBeenCalledWith(
      "Confirm reset to restore default policy values",
      "info",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Reset armed");
    expect(
      screen.getByRole("button", { name: /save defaults/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: /confirm reset configuration defaults/i,
      }),
    ).toHaveAccessibleDescription(/Reset is armed/i);

    fireEvent.click(
      screen.getByRole("button", {
        name: /confirm reset configuration defaults/i,
      }),
    );

    expect(useConfigStore.getState().searchMaxRankedResults).toBe(200);
  });

  it("sends saved payload through the real pipeline mapping", async () => {
    render(<ConfigPage />);

    fireEvent.click(screen.getByRole("button", { name: /save defaults/i }));

    await waitFor(() => expect(mocks.apiClient).toHaveBeenCalledTimes(1));

    const [, options] = mocks.apiClient.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(options).toMatchObject({ method: "PUT", token: "token" });
    expect(body.search_jurisdictions).toEqual([
      "US",
      "EP",
      "WO",
      "JP",
      "KR",
      "CN",
      "IN",
      "CA",
      "AU",
    ]);
    expect(body).not.toHaveProperty("jurisdiction");
    expect(body.hitl_enabled).toBe(false);
    expect(body.hitl_auto_skip_minutes).toBe(10);
  });

  it("locks reset while organization defaults are saving", async () => {
    let resolveSave: (value: unknown) => void = () => {};
    mocks.apiClient.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve;
        }),
    );

    render(<ConfigPage />);

    fireEvent.click(screen.getByRole("button", { name: /save defaults/i }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Saving organization defaults",
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: /prepare to reset configuration defaults/i,
        }),
      ).toBeDisabled(),
    );

    await act(async () => {
      resolveSave({});
    });
  });

  it("keeps the policy posture honest while defaults are loading", () => {
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    render(<ConfigPage />);

    expect(
      screen.getByTestId("config-defaults-status-loading"),
    ).toHaveTextContent("Loading organization defaults");
    expect(
      screen.queryByRole("button", { name: /save defaults/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Custom coverage")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
  });

  it("blocks save with an explicit unavailable-defaults posture", () => {
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(<ConfigPage />);

    const status = screen.getByTestId("config-defaults-status-unavailable");
    expect(status).toHaveTextContent("Configuration defaults unavailable");
    expect(
      screen.getByText(/Existing policy remains unchanged/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save defaults/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Custom coverage")).not.toBeInTheDocument();
  });

  it("hides cached organization defaults when configuration access is revoked", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: {
        config: {
          search_jurisdictions: ["US", "EP"],
          search_max_ranked_results: 500,
        },
      },
      isLoading: false,
      isError: true,
      error: new APIError(403, "Forbidden"),
      refetch,
    });

    render(
      <StrictMode>
        <ConfigPage />
      </StrictMode>,
    );

    expect(
      screen.getByTestId("config-defaults-status-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(
      screen.getByText("Configuration defaults access restricted"),
    ).toBeInTheDocument();
    expect(screen.getByText("Cached defaults hidden")).toBeInTheDocument();
    expect(screen.queryByText("Custom coverage")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save defaults/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /edit defaults/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry configuration load" }),
    );
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[ConfigPage] Configuration defaults access restricted",
    );
    consoleError.mockRestore();
  });

  it("keeps defaults load failure fail-closed after local rerenders", () => {
    mocks.useOrgDefaultConfig.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(<ConfigPage />);

    expect(
      screen.getByTestId("config-defaults-status-unavailable"),
    ).toHaveTextContent("Configuration defaults unavailable");
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /save defaults/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /edit defaults/i }),
    ).not.toBeInTheDocument();
  });

  it("rehydrates organization defaults when the authenticated scope changes", async () => {
    let currentToken = "token-org-a";
    mocks.useAuthToken.mockImplementation(() => currentToken);
    mocks.useOrgDefaultConfig.mockImplementation((token: string) => ({
      data: {
        config: {
          search_max_ranked_results: token === "token-org-a" ? 500 : 50,
        },
        can_manage: true,
      },
      isLoading: false,
      isError: false,
    }));

    const { rerender } = render(<ConfigPage />);
    await waitFor(() =>
      expect(useConfigStore.getState().searchMaxRankedResults).toBe(500),
    );

    currentToken = "token-org-b";
    rerender(<ConfigPage />);

    await waitFor(() =>
      expect(useConfigStore.getState().searchMaxRankedResults).toBe(50),
    );
    expect(screen.queryByText("500 ranked results")).not.toBeInTheDocument();
  });

  it("blocks save and explains the posture when signed out", () => {
    mocks.useAuthToken.mockReturnValue(null);

    render(<ConfigPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Sign in required");
    expect(screen.queryByText("Ready to save")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save defaults/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /save defaults/i }),
    ).toHaveAccessibleDescription(/Sign in to save organization defaults/i);
  });

  it("renders only one primary policy status region", () => {
    render(<ConfigPage />);

    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(
      within(screen.getByRole("status")).getByText("Ready to save"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Save state")).not.toBeInTheDocument();
    expect(screen.queryByText("Save readiness")).not.toBeInTheDocument();
  });
});
