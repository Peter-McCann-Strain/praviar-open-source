import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBar } from "@/components/shared/confidence-bar";

describe("ConfidenceBar", () => {
  it("renders a bounded score rather than probability copy", () => {
    render(<ConfidenceBar value={0.75} />);
    expect(screen.getByText("75/100")).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "Model-support score 75 out of 100; not a probability",
      ),
    ).toBeInTheDocument();
  });

  it("high confidence (0.9) gets emerald/green color class", () => {
    const { container } = render(<ConfidenceBar value={0.9} />);
    const bar = container.querySelector(".bg-success");
    expect(bar).toBeInTheDocument();
  });

  it("confidence at exactly 0.8 gets emerald/green color class", () => {
    const { container } = render(<ConfidenceBar value={0.8} />);
    const bar = container.querySelector(".bg-success");
    expect(bar).toBeInTheDocument();
  });

  it("medium confidence (0.6) gets amber color class", () => {
    const { container } = render(<ConfidenceBar value={0.6} />);
    const bar = container.querySelector(".bg-warning");
    expect(bar).toBeInTheDocument();
  });

  it("confidence at exactly 0.5 gets amber color class", () => {
    const { container } = render(<ConfidenceBar value={0.5} />);
    const bar = container.querySelector(".bg-warning");
    expect(bar).toBeInTheDocument();
  });

  it("low confidence (0.3) gets red color class", () => {
    const { container } = render(<ConfidenceBar value={0.3} />);
    const bar = container.querySelector(".bg-error");
    expect(bar).toBeInTheDocument();
  });

  it("confidence at 0.49 gets red color class", () => {
    const { container } = render(<ConfidenceBar value={0.49} />);
    const bar = container.querySelector(".bg-error");
    expect(bar).toBeInTheDocument();
  });

  it("value 0 shows 0/100", () => {
    render(<ConfidenceBar value={0} />);
    expect(screen.getByText("0/100")).toBeInTheDocument();
  });

  it("value 1 shows 100/100", () => {
    render(<ConfidenceBar value={1} />);
    expect(screen.getByText("100/100")).toBeInTheDocument();
  });

  it("renders with sm size class", () => {
    const { container } = render(<ConfidenceBar value={0.5} size="sm" />);
    const track = container.querySelector(".h-1\\.5");
    expect(track).toBeInTheDocument();
  });

  it("renders with md size class by default", () => {
    const { container } = render(<ConfidenceBar value={0.5} />);
    const track = container.querySelector(".h-2");
    expect(track).toBeInTheDocument();
  });

  it("sets the bar width style to the correct percentage", () => {
    const { container } = render(<ConfidenceBar value={0.65} />);
    const bar = container.querySelector(".bg-warning");
    expect(bar).toHaveStyle({ width: "65%" });
  });

  it("rounds fractional percentages", () => {
    render(<ConfidenceBar value={0.333} />);
    expect(screen.getByText("33/100")).toBeInTheDocument();
  });
});
