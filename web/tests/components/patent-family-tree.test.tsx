import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PatentFamilyTree } from "@/components/report/patent-family-tree";

const mockFamily = {
  family_id: "FAM-001",
  members: [
    { country: "US", doc_number: "11234567", kind: "B2" },
    { country: "US", doc_number: "20200123456", kind: "A1" },
    { country: "EP", doc_number: "3456789", kind: "A1" },
    { country: "JP", doc_number: "2021123456", kind: "A1" },
    { country: "CN", doc_number: "112345678", kind: "B1" },
  ],
};

describe("PatentFamilyTree", () => {
  it("renders family member count", () => {
    render(<PatentFamilyTree family={mockFamily} />);
    expect(
      screen.getByText(/5 members across 4 jurisdictions/),
    ).toBeInTheDocument();
  });

  it("renders country groups", () => {
    render(<PatentFamilyTree family={mockFamily} />);
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("EP")).toBeInTheDocument();
    expect(screen.getByText("JP")).toBeInTheDocument();
    expect(screen.getByText("CN")).toBeInTheDocument();
  });

  it("highlights current patent", () => {
    render(
      <PatentFamilyTree family={mockFamily} currentPatentId="US11234567B2" />,
    );
    expect(screen.getByText(/current/)).toBeInTheDocument();
  });

  it("shows empty state when no family data", () => {
    render(<PatentFamilyTree family={null} />);
    expect(
      screen.getByText("No patent family data available."),
    ).toBeInTheDocument();
  });

  it("collapses on click", () => {
    render(<PatentFamilyTree family={mockFamily} />);
    const toggle = screen.getByRole("button");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
