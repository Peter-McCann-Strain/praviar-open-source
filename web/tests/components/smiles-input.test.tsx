import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Mock MoleculeViewer2D to avoid RDKit dependency
vi.mock("@/components/chemistry/molecule-viewer-2d", () => ({
  MoleculeViewer2D: ({
    smiles,
    label,
    onRender: _onRender,
  }: {
    smiles: string;
    label?: string;
    onRender?: (s: boolean) => void;
  }) => (
    <div
      data-testid="molecule-viewer"
      data-smiles={smiles}
      data-label={label ?? ""}
    >
      Molecule Preview
    </div>
  ),
}));

import {
  SmilesInput,
  detectInputType,
  getCompoundInputReadiness,
} from "@/components/chemistry/smiles-input";

describe("SmilesInput", () => {
  const defaultProps = {
    value: "",
    onChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("renders with placeholder", () => {
    it("renders the input element", () => {
      render(<SmilesInput {...defaultProps} />);
      const input = screen.getByPlaceholderText(/succinic acid/i);
      expect(input).toBeInTheDocument();
    });

    it("labels the compound input for assistive technology", () => {
      render(<SmilesInput {...defaultProps} />);
      expect(screen.getByLabelText("Compound input")).toBeInTheDocument();
    });

    it("shows the default placeholder text", () => {
      render(<SmilesInput {...defaultProps} />);
      const input = screen.getByPlaceholderText(
        "e.g., succinic acid, OC(=O)CCC(O)=O, 110-15-6",
      );
      expect(input).toBeInTheDocument();
    });

    it("shows a custom placeholder when provided", () => {
      render(<SmilesInput {...defaultProps} placeholder="Enter compound" />);
      const input = screen.getByPlaceholderText("Enter compound");
      expect(input).toBeInTheDocument();
    });

    it("renders with pre-filled value", () => {
      render(<SmilesInput {...defaultProps} value="CCO" />);
      const input = screen.getByDisplayValue("CCO");
      expect(input).toBeInTheDocument();
    });
  });

  describe("onChange called with value", () => {
    it("calls onChange when user types in the input", () => {
      const onChange = vi.fn();
      render(<SmilesInput value="" onChange={onChange} />);
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "CCO" } });
      expect(onChange).toHaveBeenCalledWith("CCO");
    });

    it("calls onChange for each input change", () => {
      const onChange = vi.fn();
      render(<SmilesInput value="" onChange={onChange} />);
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "C" } });
      fireEvent.change(input, { target: { value: "CC" } });
      expect(onChange).toHaveBeenCalledTimes(2);
    });
  });

  describe("input type detection", () => {
    it("detects CAS Number format (digits-digits-digit)", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "110-15-6" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("CAS Number");
    });

    it("detects CAS Number format with a pasted CAS prefix", () => {
      expect(detectInputType("CAS 110-15-6")).toBe("CAS Number");
      expect(detectInputType("CAS RN 110-15-6")).toBe("CAS Number");
    });

    it("detects InChI format", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, {
        target: { value: "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3" },
      });
      expect(onInputTypeChange).toHaveBeenCalledWith("InChI");
    });

    it("detects InChIKey format (14-10-1 uppercase letters)", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, {
        target: { value: "LFQSCWFLJHTTHZ-UHFFFAOYSA-N" },
      });
      expect(onInputTypeChange).toHaveBeenCalledWith("InChIKey");
    });

    it("detects SMILES format with typical characters", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "OC(=O)CCC(O)=O" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("SMILES");
    });

    it("detects simple atom-chain SMILES", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "CCO" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("SMILES");
    });

    it("detects all-lowercase aromatic SMILES (e.g. benzene 'c1ccccc1')", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "c1ccccc1" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("SMILES");
    });

    it("keeps plain compound words as Name despite the broadened SMILES match", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "benzene" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("Name");
    });

    it("keeps common target and drug codes as Name", () => {
      expect(detectInputType("BRD4")).toBe("Name");
      expect(detectInputType("JAK1")).toBe("Name");
      expect(detectInputType("PF-07321332")).toBe("Name");
      expect(detectInputType("BMS-986165")).toBe("Name");
    });

    it("detects compound name as Name type", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value=""
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      const input = screen.getByPlaceholderText(/succinic acid/i);
      fireEvent.change(input, { target: { value: "succinic acid" } });
      expect(onInputTypeChange).toHaveBeenCalledWith("Name");
    });

    it("reports null for empty input", () => {
      const onInputTypeChange = vi.fn();
      render(
        <SmilesInput
          value="CCO"
          onChange={vi.fn()}
          onInputTypeChange={onInputTypeChange}
        />,
      );
      onInputTypeChange.mockClear();
      const input = screen.getByDisplayValue("CCO");
      fireEvent.change(input, { target: { value: "" } });
      expect(onInputTypeChange).toHaveBeenCalledWith(null);
    });

    it("displays detected type badge when input has value", () => {
      render(<SmilesInput value="110-15-6" onChange={vi.fn()} />);
      // The badge shows the detected type text
      expect(screen.getByText("CAS Number")).toBeInTheDocument();
    });

    it("displays SMILES badge for SMILES input", () => {
      render(<SmilesInput value="OC(=O)CCC(O)=O" onChange={vi.fn()} />);
      expect(screen.getByText("SMILES")).toBeInTheDocument();
    });

    it("updates the detected badge when a controlled value changes", () => {
      const { rerender } = render(
        <SmilesInput value="aspirin" onChange={vi.fn()} />,
      );
      expect(screen.getByText("Name")).toBeInTheDocument();

      rerender(<SmilesInput value="CCO" onChange={vi.fn()} />);

      expect(screen.getByText("SMILES")).toBeInTheDocument();
      expect(screen.queryByText("Name")).not.toBeInTheDocument();
    });
  });

  describe("input readiness", () => {
    it("accepts valid compound identifiers without overblocking project codes", () => {
      expect(getCompoundInputReadiness("110-15-6")).toMatchObject({
        canProceed: true,
        inputType: "CAS Number",
        label: "CAS number ready",
      });
      expect(getCompoundInputReadiness("PF-07321332")).toMatchObject({
        canProceed: true,
        inputType: "Name",
      });
      expect(getCompoundInputReadiness("BMS-986165")).toMatchObject({
        canProceed: true,
        inputType: "Name",
      });
      expect(getCompoundInputReadiness("succinic acid")).toMatchObject({
        canProceed: true,
        inputType: "Name",
      });
    });

    it("blocks CAS-shaped values with invalid checksums", () => {
      expect(getCompoundInputReadiness("110-15-7")).toMatchObject({
        canProceed: false,
        inputType: "CAS Number",
        label: "CAS checksum needs review",
        status: "malformed_identifier",
      });
    });

    it("blocks malformed structured identifiers before launch", () => {
      expect(getCompoundInputReadiness("InChI=bogus")).toMatchObject({
        canProceed: false,
        inputType: "InChI",
        label: "Malformed InChI",
      });
      expect(
        getCompoundInputReadiness("ABCDEFGHIJKLMN-ABCDEFGHIJ"),
      ).toMatchObject({
        canProceed: false,
        label: "InChIKey needs review",
      });
    });

    it("blocks obvious non-identifiers and pasted prose", () => {
      expect(getCompoundInputReadiness("!!!")).toMatchObject({
        canProceed: false,
        label: "Needs compound identifier",
      });
      expect(
        getCompoundInputReadiness("https://example.test/patent"),
      ).toMatchObject({
        canProceed: false,
        label: "Needs compound identifier",
      });
    });

    it("blocks incomplete SMILES ring or branch syntax", () => {
      expect(getCompoundInputReadiness("C1CC")).toMatchObject({
        canProceed: false,
        inputType: "SMILES",
        label: "SMILES needs review",
      });
      expect(getCompoundInputReadiness("CC(")).toMatchObject({
        canProceed: false,
        inputType: "SMILES",
      });
    });
  });

  describe("clear button", () => {
    it("shows clear button when value is present", () => {
      render(<SmilesInput value="CCO" onChange={vi.fn()} />);
      const clearButton = screen.getByTitle("Clear");
      expect(clearButton).toBeInTheDocument();
      expect(clearButton).toHaveClass("h-11", "w-11");
    });

    it("does not show clear button when value is empty", () => {
      render(<SmilesInput value="" onChange={vi.fn()} />);
      expect(screen.queryByTitle("Clear")).not.toBeInTheDocument();
    });

    it("calls onChange with empty string when clear is clicked", () => {
      const onChange = vi.fn();
      render(<SmilesInput value="CCO" onChange={onChange} />);
      const clearButton = screen.getByTitle("Clear");
      fireEvent.click(clearButton);
      expect(onChange).toHaveBeenCalledWith("");
    });
  });

  describe("paste button", () => {
    it("renders the paste button", () => {
      render(<SmilesInput {...defaultProps} />);
      const pasteButton = screen.getByTitle("Paste from clipboard");
      expect(pasteButton).toBeInTheDocument();
      expect(pasteButton).toHaveClass("h-11", "w-11");
    });
  });

  describe("molecule preview", () => {
    it("shows preview when showPreview=true and input is SMILES", () => {
      render(
        <SmilesInput
          value="OC(=O)CCC(O)=O"
          onChange={vi.fn()}
          showPreview={true}
        />,
      );
      expect(screen.getByTestId("molecule-viewer")).toBeInTheDocument();
    });

    it("wraps the structure preview in a responsive non-clipping frame", () => {
      render(
        <SmilesInput
          value="OC(=O)CCC(O)=O"
          onChange={vi.fn()}
          showPreview={true}
        />,
      );

      const frame = screen.getByTestId("smiles-preview-frame");
      expect(frame).toHaveClass("w-full", "max-w-[25rem]", "min-w-0");
      expect(frame).not.toHaveClass("overflow-hidden");
    });

    it("does not show a SMILES preview for InChI input type", () => {
      render(
        <SmilesInput
          value="InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3"
          onChange={vi.fn()}
          showPreview={true}
        />,
      );
      expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
      expect(
        screen.getByText(
          "InChI detected. Structure preview will appear after resolution.",
        ),
      ).toBeInTheDocument();
    });

    it("does not show preview for Name type", () => {
      render(
        <SmilesInput value="aspirin" onChange={vi.fn()} showPreview={true} />,
      );
      expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
    });

    it("does not show preview for CAS Number type", () => {
      render(
        <SmilesInput value="110-15-6" onChange={vi.fn()} showPreview={true} />,
      );
      expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
    });

    it("does not show preview when showPreview=false", () => {
      render(
        <SmilesInput
          value="OC(=O)CCC(O)=O"
          onChange={vi.fn()}
          showPreview={false}
        />,
      );
      expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
    });

    it("does not show preview when value is empty", () => {
      render(<SmilesInput value="" onChange={vi.fn()} showPreview={true} />);
      expect(screen.queryByTestId("molecule-viewer")).not.toBeInTheDocument();
    });
  });

  describe("className prop", () => {
    it("applies custom className to the wrapper", () => {
      const { container } = render(
        <SmilesInput {...defaultProps} className="my-custom-class" />,
      );
      expect(container.firstElementChild?.className).toContain(
        "my-custom-class",
      );
    });
  });

  describe("pre-filled value type detection on mount", () => {
    it("detects type of pre-filled SMILES value on mount", () => {
      render(<SmilesInput value="OC(=O)CCC(O)=O" onChange={vi.fn()} />);
      expect(screen.getByText("SMILES")).toBeInTheDocument();
    });

    it("shows type badge for pre-filled CAS Number on mount", () => {
      render(<SmilesInput value="110-15-6" onChange={vi.fn()} />);
      expect(screen.getByText("CAS Number")).toBeInTheDocument();
    });
  });
});
