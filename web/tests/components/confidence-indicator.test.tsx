import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceIndicator } from "@/components/report/confidence-indicator";

vi.mock("@/components/shared/confidence-bar", () => ({
  ConfidenceBar: ({ value }: any) => (
    <div data-testid="confidence-bar">{value}</div>
  ),
}));

describe("ConfidenceIndicator", () => {
  it("shows high model support for value >= 0.8", () => {
    render(<ConfidenceIndicator value={0.85} />);
    expect(screen.getByText("High model support")).toBeDefined();
  });

  it("shows moderate model support for value 0.5-0.79", () => {
    render(<ConfidenceIndicator value={0.65} />);
    expect(screen.getByText("Moderate model support")).toBeDefined();
  });

  it("shows low model support for value < 0.5", () => {
    render(<ConfidenceIndicator value={0.3} />);
    expect(screen.getByText("Low model support")).toBeDefined();
  });

  it("does not show bar when showBar is false", () => {
    render(<ConfidenceIndicator value={0.8} />);
    expect(screen.queryByTestId("confidence-bar")).toBeNull();
  });

  it("shows bar when showBar is true", () => {
    render(<ConfidenceIndicator value={0.8} showBar={true} />);
    expect(screen.getByTestId("confidence-bar")).toBeDefined();
  });

  it("boundary: 0.8 is high support", () => {
    render(<ConfidenceIndicator value={0.8} />);
    expect(screen.getByText("High model support")).toBeDefined();
  });

  it("boundary: 0.5 is moderate support", () => {
    render(<ConfidenceIndicator value={0.5} />);
    expect(screen.getByText("Moderate model support")).toBeDefined();
  });

  it("boundary: 0.49 is low support", () => {
    render(<ConfidenceIndicator value={0.49} />);
    expect(screen.getByText("Low model support")).toBeDefined();
  });
});
