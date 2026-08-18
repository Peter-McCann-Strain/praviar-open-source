import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  formatSelectedJurisdictionCount,
  nextSearchJurisdictions,
} from "@/components/analysis-wizard/configuration-search-parameters-helpers";
import { ConfigurationSearchParameters } from "@/components/analysis-wizard/configuration-search-parameters";
import { ConfigurationSearchParametersJurisdictions } from "@/components/analysis-wizard/configuration-search-parameters-jurisdictions";
import { ConfigurationSearchParametersSliders } from "@/components/analysis-wizard/configuration-search-parameters-sliders";
import type { ConfigState } from "@/stores/config-store";

describe("configuration-search-parameters helpers", () => {
  it("formats the jurisdiction count copy", () => {
    expect(formatSelectedJurisdictionCount(1)).toBe(
      "1 jurisdiction selected — the exact scope is recorded with the run",
    );
    expect(formatSelectedJurisdictionCount(3)).toBe(
      "3 jurisdictions selected — the exact scope is recorded with the run",
    );
  });

  it("adds and removes jurisdictions without emptying the selection", () => {
    expect(nextSearchJurisdictions(["US", "EP"], "JP", true)).toEqual([
      "US",
      "EP",
      "JP",
    ]);
    expect(nextSearchJurisdictions(["US", "EP"], "EP", false)).toEqual(["US"]);
    expect(nextSearchJurisdictions(["US"], "US", false)).toBeNull();
  });
});

describe("configuration-search-parameters components", () => {
  const createConfig = (): ConfigState =>
    ({
      searchTanimotoThreshold: 0.55,
      searchMaxRankedResults: 200,
      includeExpired: true,
      citationTraversalEnabled: true,
      citationMaxDepth: 2,
      searchJurisdictions: ["US", "EP"],
      enablePubchem: true,
      enableBigquery: true,
      enableSurechembl: true,
      enablePatcid: true,
      setConfig: vi.fn(),
    }) as unknown as ConfigState;

  it("renders the search parameter section shell with the composed subsections", () => {
    render(<ConfigurationSearchParameters config={createConfig()} />);

    expect(screen.getByText("Search Parameters")).toBeInTheDocument();
    expect(screen.getByText("Tanimoto Threshold")).toBeInTheDocument();
    expect(screen.getByText("Ranked Result Budget")).toBeInTheDocument();
    expect(screen.getByText("Search Jurisdictions")).toBeInTheDocument();
    expect(screen.getByText("Include Expired Patents")).toBeInTheDocument();
    expect(screen.getByText("Citation Expansion")).toBeInTheDocument();
    expect(screen.getByText("Patent Sources")).toBeInTheDocument();
  });

  it("updates the search sliders through the leaf component", () => {
    const config = createConfig();

    render(<ConfigurationSearchParametersSliders config={config} />);

    const sliders = screen.getAllByRole("slider");
    expect(screen.getByLabelText("Ranked Result Budget")).toHaveAttribute(
      "min",
      "50",
    );
    fireEvent.change(sliders[0], { target: { value: "0.7" } });
    fireEvent.change(sliders[1], { target: { value: "250" } });

    expect(config.setConfig).toHaveBeenNthCalledWith(1, {
      searchTanimotoThreshold: 0.7,
    });
    expect(config.setConfig).toHaveBeenNthCalledWith(2, {
      searchMaxRankedResults: 250,
    });
  });

  it("disables the final selected jurisdiction with explanatory copy", () => {
    const config = createConfig();
    config.searchJurisdictions = ["US"];

    render(<ConfigurationSearchParametersJurisdictions config={config} />);

    expect(
      screen.getByText("At least one jurisdiction is required for launch."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Select United States (US)")).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Select United States (US)"));

    expect(config.setConfig).not.toHaveBeenCalled();
  });
});
