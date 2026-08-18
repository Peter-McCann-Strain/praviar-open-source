import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfigurationBasics } from "@/components/analysis-wizard/configuration-basics";
import type { ConfigState } from "@/stores/config-store";

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

describe("ConfigurationBasics", () => {
  it("lets the user switch jurisdiction bundles", () => {
    const config = createConfig();

    render(
      <ConfigurationBasics
        config={config}
        showSavePreset={false}
        presetName=""
        presetDescription=""
        isSavingPreset={false}
        sessionReady
        sessionError={null}
        onLoadPreset={vi.fn()}
        onToggleSavePreset={vi.fn()}
        onPresetNameChange={vi.fn()}
        onPresetDescriptionChange={vi.fn()}
        onCancelSavePreset={vi.fn()}
        onSavePreset={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: /europe \+ uk/i }));
    expect(config.applyJurisdictionBundle).toHaveBeenCalledWith("europe_uk");
    expect(
      screen.getByRole("radio", { name: /major markets/i }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("radiogroup", { name: "Jurisdiction bundle" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Launch-ready lanes:/i)).toBeInTheDocument();
  });

  it("shows custom target controls and forwards toggle events", () => {
    const config = createConfig({
      jurisdictionBundle: "custom",
      targetJurisdictions: ["US", "UK"],
    });

    render(
      <ConfigurationBasics
        config={config}
        showSavePreset={false}
        presetName=""
        presetDescription=""
        isSavingPreset={false}
        sessionReady
        sessionError={null}
        onLoadPreset={vi.fn()}
        onToggleSavePreset={vi.fn()}
        onPresetNameChange={vi.fn()}
        onPresetDescriptionChange={vi.fn()}
        onCancelSavePreset={vi.fn()}
        onSavePreset={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "JP" }));
    expect(config.toggleTargetJurisdiction).toHaveBeenCalledWith("JP");
    expect(
      screen.getByText(/staged in this frontend slice: UK/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Custom target jurisdictions" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "US" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("checkbox", { name: "US" })).toHaveClass(
      "min-h-11",
    );
  });

  it("labels preset controls and allows the same preset to be reloaded", () => {
    const onLoadPreset = vi.fn();

    render(
      <ConfigurationBasics
        config={createConfig()}
        savedPresets={[
          {
            id: "preset-1",
            name: "Counsel baseline",
            description: "Major-market review",
            config: { max_analysis_patents: 15 },
          },
        ]}
        showSavePreset={true}
        presetName=""
        presetDescription=""
        isSavingPreset={false}
        sessionReady
        sessionError={null}
        onLoadPreset={onLoadPreset}
        onToggleSavePreset={vi.fn()}
        onPresetNameChange={vi.fn()}
        onPresetDescriptionChange={vi.fn()}
        onCancelSavePreset={vi.fn()}
        onSavePreset={vi.fn()}
      />,
    );

    const presetSelect = screen.getByLabelText("Load saved configuration");
    const savePresetButton = screen.getByRole("button", {
      name: "Save as Preset",
    });
    fireEvent.change(presetSelect, { target: { value: "preset-1" } });
    fireEvent.change(presetSelect, { target: { value: "preset-1" } });

    expect(onLoadPreset).toHaveBeenCalledTimes(2);
    expect(savePresetButton).toHaveAttribute("aria-expanded", "true");
    expect(savePresetButton).toHaveAttribute("aria-controls");
    expect(presetSelect).toHaveClass("min-h-11");
    expect(savePresetButton).toHaveClass("min-h-11");
    expect(screen.getByLabelText("Name")).toHaveClass("min-h-11");
    expect(screen.getByLabelText("Description (optional)")).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass(
      "min-h-11",
    );
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass(
      "min-h-11",
    );
  });

  it("presents adaptive execution without user-facing depth presets", () => {
    render(
      <ConfigurationBasics
        config={createConfig()}
        showSavePreset={false}
        presetName=""
        presetDescription=""
        isSavingPreset={false}
        sessionReady
        sessionError={null}
        onLoadPreset={vi.fn()}
        onToggleSavePreset={vi.fn()}
        onPresetNameChange={vi.fn()}
        onPresetDescriptionChange={vi.fn()}
        onCancelSavePreset={vi.fn()}
        onSavePreset={vi.fn()}
      />,
    );

    expect(screen.getByText("Adaptive Execution")).toBeInTheDocument();
    expect(screen.getByText("One adaptive path")).toBeInTheDocument();
    expect(screen.getByText("Evidence gates")).toBeInTheDocument();
    expect(screen.queryByText("Analysis Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("Quick Scan")).not.toBeInTheDocument();
    expect(screen.queryByText("Standard")).not.toBeInTheDocument();
    expect(screen.queryByText("Thorough")).not.toBeInTheDocument();
  });

  it("disables preset saving while the secure session is preparing", () => {
    render(
      <ConfigurationBasics
        config={createConfig()}
        showSavePreset={false}
        presetName=""
        presetDescription=""
        isSavingPreset={false}
        sessionReady={false}
        sessionError="Session unavailable"
        onLoadPreset={vi.fn()}
        onToggleSavePreset={vi.fn()}
        onPresetNameChange={vi.fn()}
        onPresetDescriptionChange={vi.fn()}
        onCancelSavePreset={vi.fn()}
        onSavePreset={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Save as Preset" }),
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing secure session",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Session unavailable");
  });
});
