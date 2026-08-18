import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CompoundInputStep } from "@/components/analysis-wizard/compound-input-step";
import { detectInputType } from "@/components/chemistry/smiles-input";

vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ smiles }: { smiles: string }) => (
    <div data-testid="molecule-viewer" data-smiles={smiles}>
      Molecule Preview
    </div>
  ),
}));

describe("compound input classifier contract", () => {
  it.each([
    ["CO", "SMILES"],
    ["[C@@H](N)C(=O)O", "SMILES"],
    ["[NH4+]", "SMILES"],
    ["boron", "Name"],
    ["iron", "Name"],
    ["kdYfgrwqoybrfd-uhfffaoysa-n", "InChIKey"],
    ["\u0665\u0660-\u0667\u0668-\u0662", "Name"],
    ["\u212aDYFGRWQOYBRFD-UHFFFAOYSA-N", "Name"],
    ["\uFEFFCCO\uFEFF", "SMILES"],
    ["CAS\u00A050-78-2", "CAS Number"],
    ["CAS\u202F50-78-2", "CAS Number"],
    ["[C\u0085]", "SMILES"],
    ["[C\u001C]", "SMILES"],
    ["[C\uFEFF]", "Name"],
  ] as const)("classifies %s as %s", (value, expected) => {
    expect(detectInputType(value)).toBe(expected);
  });
});

describe("CompoundInputStep", () => {
  it("renders the compound workbench and keeps next disabled without input", () => {
    render(
      <CompoundInputStep
        compoundInput=""
        onCompoundInputChange={vi.fn()}
        onInputTypeChange={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    expect(screen.getByText("Molecule intake")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("Name, SMILES, InChI, CAS"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent("Awaiting compound");
    expect(
      screen.getByRole("button", { name: /Next: Configure/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Next: Configure/i }),
    ).toHaveClass("min-h-11", "w-full", "sm:w-auto");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Compound input awaiting identifier",
    );
  });

  it("selecting an example updates the compound and detected input type", () => {
    const onCompoundInputChange = vi.fn();
    const onInputTypeChange = vi.fn();

    render(
      <CompoundInputStep
        compoundInput=""
        onCompoundInputChange={onCompoundInputChange}
        onInputTypeChange={onInputTypeChange}
        onNext={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Aspirin/i }));

    expect(onCompoundInputChange).toHaveBeenCalledWith("aspirin");
    expect(onInputTypeChange).toHaveBeenCalledWith("Name");
  });

  it("requires explicit identity confirmation before enabling the next step", () => {
    const onNext = vi.fn();
    const onConfirmIdentity = vi.fn();

    render(
      <CompoundInputStep
        compoundInput="OC(=O)CCC(O)=O"
        onCompoundInputChange={vi.fn()}
        onConfirmIdentity={onConfirmIdentity}
        onInputTypeChange={vi.fn()}
        onNext={onNext}
      />,
    );

    const next = screen.getByRole("button", { name: /Next: Configure/i });
    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent("SMILES detected");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Detected input type: SMILES. SMILES syntax looks complete.",
    );
    expect(
      screen.getByTestId("compound-identity-decision-sheet"),
    ).toHaveTextContent("Pending authoritative resolution");
    expect(
      screen.getByTestId("compound-identity-decision-sheet"),
    ).toHaveTextContent("No explicit variant in contract");
    expect(next).toBeDisabled();

    fireEvent.click(
      screen.getByRole("button", { name: "Confirm for resolution" }),
    );
    expect(onConfirmIdentity).toHaveBeenCalledTimes(1);
    expect(onNext).not.toHaveBeenCalled();
  });

  it("continues only after the exact identity is confirmed", () => {
    const onNext = vi.fn();

    render(
      <CompoundInputStep
        compoundInput="OC(=O)CCC(O)=O"
        identityConfirmed
        onCompoundInputChange={vi.fn()}
        onInputTypeChange={vi.fn()}
        onNext={onNext}
      />,
    );

    const next = screen.getByRole("button", { name: /Next: Configure/i });
    expect(next).toBeEnabled();
    fireEvent.click(next);

    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("blocks obvious non-compound input before configuration", () => {
    render(
      <CompoundInputStep
        compoundInput="!!!"
        onCompoundInputChange={vi.fn()}
        onInputTypeChange={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent("Needs compound identifier");
    expect(
      screen.getByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Correct before confirming");
    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent(
      "Enter a compound name, code, SMILES, InChI, InChIKey, or CAS number.",
    );
    expect(
      screen.getByRole("button", { name: /Next: Configure/i }),
    ).toBeDisabled();
  });

  it("keeps valid internal drug codes launch-ready", () => {
    const onNext = vi.fn();

    render(
      <CompoundInputStep
        compoundInput="PF-07321332"
        identityConfirmed
        onCompoundInputChange={vi.fn()}
        onInputTypeChange={vi.fn()}
        onNext={onNext}
      />,
    );

    const next = screen.getByRole("button", { name: /Next: Configure/i });
    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent("Identifier ready");
    expect(
      screen.getByTestId("compound-action-readiness-summary"),
    ).toHaveTextContent(
      "Name or project code accepted. Structure resolution is checked before claim search.",
    );
    expect(next).toBeEnabled();

    fireEvent.click(next);

    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("keeps the launch navigation before deeper preflight context", () => {
    render(
      <CompoundInputStep
        compoundInput="aspirin"
        matterScopeSlot={<section>Matter scope preflight</section>}
        onCompoundInputChange={vi.fn()}
        onInputTypeChange={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    expect(screen.getByText("Matter scope preflight")).toBeInTheDocument();
    expect(
      screen
        .getByTestId("compound-intake-action-bar")
        .compareDocumentPosition(screen.getByText("Matter scope preflight")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("confirms explicitly and focuses the identifier for correction", () => {
    const onConfirmIdentity = vi.fn();

    render(
      <CompoundInputStep
        compoundInput="aspirin"
        identityConfirmed={false}
        onCompoundInputChange={vi.fn()}
        onConfirmIdentity={onConfirmIdentity}
        onInputTypeChange={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Confirm for resolution" }),
    );
    expect(onConfirmIdentity).toHaveBeenCalledTimes(1);

    const input = screen.getByPlaceholderText("Name, SMILES, InChI, CAS");
    fireEvent.click(screen.getByRole("button", { name: "Correct identifier" }));

    expect(input).toHaveFocus();
    expect(input).toHaveProperty("selectionStart", 0);
    expect(input).toHaveProperty("selectionEnd", "aspirin".length);
  });
});
