import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceLaunchVisual } from "@/components/brand";

describe("EvidenceLaunchVisual", () => {
  it("renders a branded evidence launch visual with an accessible label", () => {
    const { container } = render(
      <EvidenceLaunchVisual label="Launch evidence preview" />,
    );

    const visual = screen.getByLabelText("Launch evidence preview");
    expect(visual).toBeInTheDocument();
    expect(visual).toHaveAttribute("data-praviar-visual", "evidence-launch");
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("avoids retired ring or molecule pseudo-logo motifs", () => {
    const { container } = render(
      <EvidenceLaunchVisual label="Launch evidence preview" />,
    );

    const svg = container.querySelector("svg");
    const pathData = [...container.querySelectorAll("path")]
      .map((path) => path.getAttribute("d") ?? "")
      .join(" ");

    expect(svg).toBeInTheDocument();
    expect(pathData).not.toContain("M132 82 178 108v53l-46 27-46-27");
    expect(pathData).not.toContain("M43 0 108 13l24 55-42 49");
  });

  it("supports the compact launch-panel variant", () => {
    render(<EvidenceLaunchVisual compact label="Compact evidence map" />);

    expect(screen.getByLabelText("Compact evidence map")).toHaveClass(
      "min-h-[168px]",
    );
  });
});
