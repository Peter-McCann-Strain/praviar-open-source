import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CompoundIdentityDecisionSheet } from "@/components/analysis-wizard/compound-identity-decision-sheet";

describe("CompoundIdentityDecisionSheet", () => {
  it("separates submitted input from unresolved canonical identity", () => {
    const onConfirm = vi.fn();

    render(
      <CompoundIdentityDecisionSheet
        canConfirm={true}
        compoundInput="  aspirin  "
        inputType="Name"
        isConfirmed={false}
        onConfirm={onConfirm}
        onCorrect={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Submitted input → resolved search identity",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("aspirin")).toBeInTheDocument();
    expect(
      screen.getByText("Pending authoritative resolution"),
    ).toBeInTheDocument();
    expect(screen.getByText("Pending resolved structure")).toBeInTheDocument();
    expect(screen.getByText("Not declared")).toBeInTheDocument();
    expect(
      screen.getByText("No explicit variant in contract"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not expose a separate tautomer-normalized/i),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Confirm for resolution" }),
    );

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("surfaces multi-fragment and stereochemical provenance without claiming resolution", () => {
    render(
      <CompoundIdentityDecisionSheet
        canConfirm={true}
        compoundInput="C[C@H](O)C.Cl"
        inputType="SMILES"
        isConfirmed={false}
        onConfirm={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Multi-fragment input detected"),
    ).toBeInTheDocument();
    expect(screen.getByText("atom markers submitted")).toBeInTheDocument();
    expect(
      screen.getByText(/2D preview checks browser renderability only/i),
    ).toBeInTheDocument();
  });

  it("distinguishes a declared product form from a canonical search transform", () => {
    render(
      <CompoundIdentityDecisionSheet
        canConfirm={true}
        compoundInput="aspirin"
        inputType="Name"
        isConfirmed={true}
        onConfirm={vi.fn()}
        onCorrect={vi.fn()}
        saltPolymorphForm="Free base, Form A"
      />,
    );

    expect(screen.getByText("Declared: Free base, Form A")).toBeInTheDocument();
    expect(
      screen.getByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Confirmed for resolution");
    expect(
      screen.getByRole("button", {
        name: "Submitted identity confirmed",
      }),
    ).toBeInTheDocument();
  });

  it("keeps malformed identifiers unconfirmable and offers correction", () => {
    const onConfirm = vi.fn();
    const onCorrect = vi.fn();

    render(
      <CompoundIdentityDecisionSheet
        canConfirm={false}
        compoundInput="!!!"
        inputType="Name"
        isConfirmed={false}
        onConfirm={onConfirm}
        onCorrect={onCorrect}
      />,
    );

    expect(
      screen.getByTestId("compound-identity-confirmation-status"),
    ).toHaveTextContent("Correct before confirming");
    const confirmButton = screen.getByRole("button", {
      name: "Confirm for resolution",
    });
    expect(confirmButton).toBeDisabled();

    fireEvent.click(confirmButton);
    fireEvent.click(screen.getByRole("button", { name: "Correct identifier" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCorrect).toHaveBeenCalledTimes(1);
  });
});
