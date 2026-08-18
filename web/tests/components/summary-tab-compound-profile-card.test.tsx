import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CompoundProfileCard } from "@/components/report/summary-tab-compound-profile-card";
import { TEST_REPORT } from "../fixtures/report-fixture";

vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ label }: { label?: string }) => (
    <div data-testid="molecule-viewer">{label}</div>
  ),
}));

describe("CompoundProfileCard", () => {
  it("shows submitted, resolved, and broadened search identities without conflating them", () => {
    render(
      <CompoundProfileCard
        report={{
          ...TEST_REPORT,
          compound: {
            ...TEST_REPORT.compound,
            original_input: "succinic acid disodium salt",
            input_type: "name",
            free_base_smiles: "OC(=O)CCC(O)=O",
            stereo_stripped_smiles: "OC(=O)CCC(O)=O",
          },
        }}
      />,
    );

    const identity = screen.getByTestId("compound-identity-resolution");
    expect(
      within(identity).getByRole("heading", {
        name: "Submitted input → resolved identity → search variants",
      }),
    ).toBeInTheDocument();
    expect(
      within(identity).getByText("succinic acid disodium salt"),
    ).toBeInTheDocument();
    expect(within(identity).getByText("1 · Submitted")).toBeInTheDocument();
    expect(
      within(identity).getByText("2 · Canonical resolution"),
    ).toBeInTheDocument();
    expect(
      within(identity).getByText("3 · Retrieval variants"),
    ).toBeInTheDocument();
    expect(within(identity).getAllByText("OC(=O)CCC(O)=O")).toHaveLength(3);
    expect(
      within(identity).getByText(
        /tautomer-normalized structure is not emitted/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(identity).getByText(
        /Broadened search forms extend retrieval and do not replace/i,
      ),
    ).toBeInTheDocument();
  });

  it("fails visibly when broadened search variants are not emitted", () => {
    render(<CompoundProfileCard report={TEST_REPORT} />);

    const identity = screen.getByTestId("compound-identity-resolution");
    expect(within(identity).getAllByText("Not emitted")).toHaveLength(2);
  });

  it("uses stacked related-compound cards on mobile instead of squeezing table columns", () => {
    render(<CompoundProfileCard report={TEST_REPORT} />);

    const mobileList = screen.getByRole("list", { name: "Related compounds" });
    const mobileItems = within(mobileList).getAllByRole("listitem");

    expect(mobileList).toHaveClass("sm:hidden");
    expect(mobileItems).toHaveLength(
      TEST_REPORT.compound.related_compounds.length,
    );
    expect(within(mobileItems[0]).getByText("citric acid")).toBeInTheDocument();
    expect(within(mobileItems[0]).getByText("61% match")).toBeInTheDocument();
    expect(
      within(mobileItems[0]).getByRole("progressbar", {
        name: "citric acid similarity",
      }),
    ).toHaveAttribute("aria-valuenow", "61");
  });

  it("keeps a focusable, minimum-width comparison table for larger viewports", () => {
    render(<CompoundProfileCard report={TEST_REPORT} />);

    const desktopRegion = screen.getByRole("region", {
      name: "Related compounds horizontal scroll area",
    });
    const table = within(desktopRegion).getByRole("table");

    expect(desktopRegion).toHaveClass("hidden", "sm:block");
    expect(desktopRegion).toHaveAttribute("tabindex", "0");
    expect(table).toHaveClass("min-w-[28rem]");
    expect(
      within(table).getByRole("columnheader", { name: "Tanimoto" }),
    ).toBeInTheDocument();
  });
});
