import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { DrawingStructureCard } from "@/components/report/drawing-structure-card";
import type { DrawingStructure } from "@praviar/shared-types";

vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({ smiles, isMarkush }: any) => (
    <div
      data-testid="molecule-viewer"
      data-smiles={smiles}
      data-is-markush={String(isMarkush ?? false)}
    />
  ),
}));

const REGULAR: DrawingStructure = {
  patent_id: "US0000000018A1",
  page_number: 20,
  structure_index: 0,
  canonical_smiles: "CC(=O)Oc1ccccc1C(=O)O",
  confidence: 0.92,
  extraction_tool: "ensemble:cascade",
  input_image_sha256: "a".repeat(64),
  source_page_image_sha256: "b".repeat(64),
  is_markush: false,
};

const MARKUSH: DrawingStructure = {
  patent_id: "US0000000019A1",
  page_number: 6,
  structure_index: 0,
  canonical_smiles: "",
  markush_cxsmiles: "[*:1]Cc1ccc(C(=O)N[*:2])cc1",
  markush_r_groups: ["R1: alkyl", "R2: aryl"],
  confidence: 0,
  extraction_tool: "markushgrapher",
  is_markush: true,
  rdkit_valid: true,
  markush_scope_verdict: {
    verdict: "ambiguous",
    abstained_reason: "Substituent table requires chemistry review.",
  },
};

const LOW_CONF: DrawingStructure = {
  ...REGULAR,
  confidence: 0.42,
};

describe("DrawingStructureCard", () => {
  it("renders a regular molecule with canonical SMILES", () => {
    render(<DrawingStructureCard structure={REGULAR} />);
    const viewer = screen.getByTestId("molecule-viewer");
    expect(viewer).toHaveAttribute("data-smiles", REGULAR.canonical_smiles);
    expect(viewer).toHaveAttribute("data-is-markush", "false");
    // No Markush badge on a regular structure
    expect(screen.queryByText("Markush")).not.toBeInTheDocument();
    expect(screen.getByText("Inputs bound")).toBeInTheDocument();
    expect(screen.getByText("ensemble:cascade")).toBeInTheDocument();
    expect(screen.getByText("sha256:aaaaaaaaaaaa…")).toBeInTheDocument();
    expect(screen.getByText("sha256:bbbbbbbbbbbb…")).toBeInTheDocument();
  });

  it("renders a Markush structure with CXSMILES, badge, and R-group count", () => {
    render(<DrawingStructureCard structure={MARKUSH} />);
    const viewer = screen.getByTestId("molecule-viewer");
    expect(viewer).toHaveAttribute("data-smiles", MARKUSH.markush_cxsmiles);
    expect(viewer).toHaveAttribute("data-is-markush", "true");
    expect(screen.getByText("Markush")).toBeInTheDocument();
    expect(screen.getByText(/2 R-groups/)).toBeInTheDocument();
    expect(screen.getByText("Score not provided")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.getByText("Structure parsed")).toBeInTheDocument();
    expect(screen.getByText("Scope: Ambiguous")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Scope review abstained: Substituent table requires chemistry review.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "OCSR confidence score not provided by MarkushGrapher",
      ),
    ).toBeInTheDocument();
  });

  it("displays the confidence as a percentage badge", () => {
    render(<DrawingStructureCard structure={REGULAR} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("renders the SMILES in a copyable code-block for regular molecules", () => {
    render(<DrawingStructureCard structure={REGULAR} />);
    expect(screen.getByText(REGULAR.canonical_smiles!)).toBeInTheDocument();
    expect(screen.getByLabelText(/Copy SMILES/i)).toHaveClass("h-11", "w-11");
  });

  it("renders the CXSMILES in the code-block for Markush", () => {
    render(<DrawingStructureCard structure={MARKUSH} />);
    expect(screen.getByText(MARKUSH.markush_cxsmiles!)).toBeInTheDocument();
  });

  it("invokes clipboard.writeText with the right SMILES on copy", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: { writeText },
      writable: true,
      configurable: true,
    });
    render(<DrawingStructureCard structure={REGULAR} />);
    fireEvent.click(screen.getByLabelText(/Copy SMILES/i));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(REGULAR.canonical_smiles);
    });
  });

  it("includes patent id, page, and structure index in the header", () => {
    render(<DrawingStructureCard structure={REGULAR} />);
    expect(screen.getByText(/US0000000018A1.*p\.20.*#0/)).toBeInTheDocument();
  });

  it("renders no-SMILES placeholder when both canonical and CXSMILES are empty", () => {
    const empty: DrawingStructure = {
      ...REGULAR,
      canonical_smiles: "",
      raw_smiles: undefined,
    };
    render(<DrawingStructureCard structure={empty} />);
    expect(screen.getByText(/No SMILES extracted/)).toBeInTheDocument();
    expect(screen.getByTestId("drawing-no-smiles-placeholder")).toHaveClass(
      "w-full",
      "max-w-[280px]",
    );
    expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
  });

  it("uses a destructive badge variant for low confidence", () => {
    render(<DrawingStructureCard structure={LOW_CONF} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("warns when the exact source inputs are not bound", () => {
    render(
      <DrawingStructureCard
        structure={{
          ...REGULAR,
          input_image_sha256: "",
          source_page_image_sha256: undefined,
        }}
      />,
    );

    expect(screen.getByText("Source binding missing")).toBeInTheDocument();
    expect(screen.getAllByText("Not recorded")).toHaveLength(2);
  });

  it("preserves a fused confidence score for a Markush result from another tool", () => {
    render(
      <DrawingStructureCard
        structure={{
          ...MARKUSH,
          confidence: 0.88,
          extraction_tool: "ensemble:cascade",
        }}
      />,
    );

    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.queryByText("Score not provided")).not.toBeInTheDocument();
  });
});
