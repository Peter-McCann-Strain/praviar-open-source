import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatterScopePreflight } from "@/components/analysis-wizard/matter-scope-preflight";
import type { MatterScopePreflightValue } from "@/types/pipeline";

const DEFAULT_SCOPE: MatterScopePreflightValue = {
  assetTypeHint: "small_molecule",
  developmentStage: "discovery",
  intendedActions: ["diligence_screen"],
};

function Harness({
  compoundInput = "aspirin",
  inputType = "Name",
}: {
  compoundInput?: string;
  inputType?: string | null;
}) {
  const [value, setValue] = useState<MatterScopePreflightValue>(DEFAULT_SCOPE);

  return (
    <>
      <MatterScopePreflight
        compoundInput={compoundInput}
        inputType={inputType}
        value={value}
        onChange={setValue}
      />
      <output data-testid="matter-scope-state">{JSON.stringify(value)}</output>
    </>
  );
}

describe("MatterScopePreflight", () => {
  it("renders the governed matter-scope controls", () => {
    render(<Harness />);

    expect(
      screen.getByRole("region", { name: "Matter scope preflight" }),
    ).toBeInTheDocument();
    expect(screen.getByText("What are we clearing?")).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Small molecule/i }),
    ).toHaveAttribute("aria-checked", "true");
    const clinicalStage = within(
      screen.getByRole("radiogroup", { name: "Development stage" }),
    ).getByRole("radio", { name: "Clinical" });
    expect(clinicalStage).toHaveAttribute("aria-checked", "false");
    expect(clinicalStage).toHaveClass("min-h-11");
    expect(
      screen.getByRole("checkbox", { name: /Diligence screen/i }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("applies a bounded preflight suggestion from compound context", () => {
    render(
      <Harness
        compoundInput="oral dosage formulation with excipient blend"
        inputType="Name"
      />,
    );

    const applySuggestion = screen.getByRole("button", {
      name: "Apply suggestion",
    });
    expect(applySuggestion).toHaveClass("min-h-11");
    fireEvent.click(applySuggestion);

    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"assetTypeHint":"formulation"',
    );
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"intendedActions":["formulation_review","diligence_screen"]',
    );
  });

  it("keeps valid InChIKey suggestions on a keyboard-reachable asset option", () => {
    render(
      <Harness
        compoundInput="BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        inputType="InChIKey"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));

    const selectedAsset = screen.getByRole("radio", {
      name: /Small molecule/i,
    });

    expect(selectedAsset).toHaveAttribute("aria-checked", "true");
    expect(selectedAsset).toHaveAttribute("tabindex", "0");
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"assetTypeHint":"small_molecule"',
    );
  });

  it("does not apply an unresolved suggestion before compound input exists", () => {
    render(<Harness compoundInput="" inputType={null} />);

    expect(
      screen.getByText("Enter a compound to refine the evidence scope."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Apply suggestion" }),
    ).toBeDisabled();
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"assetTypeHint":"small_molecule"',
    );
  });

  it("updates asset, stage, and actions while keeping one intended action", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("radio", { name: /Process\/synthesis/i }));
    fireEvent.click(
      within(
        screen.getByRole("radiogroup", { name: "Development stage" }),
      ).getByRole("radio", { name: "Clinical" }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Design-around/i }));

    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"assetTypeHint":"process_or_synthesis"',
    );
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"developmentStage":"clinical"',
    );
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"design_around"',
    );

    fireEvent.click(
      screen.getByRole("checkbox", { name: /Diligence screen/i }),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Design-around/i }));

    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"intendedActions":["diligence_screen"]',
    );
  });

  it("supports keyboard navigation for radio-style scope controls", () => {
    render(<Harness />);

    fireEvent.keyDown(screen.getByRole("radio", { name: /Small molecule/i }), {
      key: "ArrowRight",
    });

    expect(
      screen.getByRole("radio", { name: /Markush candidate/i }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"assetTypeHint":"markush_candidate"',
    );

    fireEvent.keyDown(
      within(
        screen.getByRole("radiogroup", { name: "Development stage" }),
      ).getByRole("radio", { name: "Discovery" }),
      { key: "End" },
    );

    expect(
      within(
        screen.getByRole("radiogroup", { name: "Development stage" }),
      ).getByRole("radio", { name: "Commercial" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("matter-scope-state")).toHaveTextContent(
      '"developmentStage":"commercial"',
    );
  });
});
