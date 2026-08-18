import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

let mockReducedMotion = false;
import { createMotionMock } from "../helpers/mock-motion";

vi.mock("motion/react", () =>
  createMotionMock({
    useReducedMotion: () => mockReducedMotion,
  }),
);

import { PipelineComparison } from "@/components/landing/pipeline-comparison";
import { PipelineComparisonExecutionPanel } from "@/components/landing/pipeline-comparison-execution-panel";
import type { TraceStep } from "@/components/landing/pipeline-comparison-data";

const MASK_TEST_STEPS: TraceStep[] = Array.from({ length: 8 }, (_, index) => ({
  type: "step",
  text: `Mask step ${index + 1}`,
  delay: index,
}));

describe("PipelineComparison", () => {
  beforeEach(() => {
    mockReducedMotion = false;
  });

  it("renders the section heading", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(
        /One review path, with deeper evidence when the record requires it/,
      ),
    ).toBeInTheDocument();
  });

  it("renders the adaptive timeline panel header", () => {
    render(<PipelineComparison />);
    expect(screen.getByText("Adaptive Evidence Timeline")).toBeInTheDocument();
  });

  it("renders the subtitle pill", () => {
    render(<PipelineComparison />);
    expect(screen.getByText("Adaptive evidence path")).toBeInTheDocument();
  });

  it("shows the single-path tagline", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(/One path.*escalates only when the record demands it/),
    ).toBeInTheDocument();
  });

  it("shows the representative input immediately", () => {
    render(<PipelineComparison />);
    const inputs = screen.getAllByText(/Compound \+ patent claims/);
    expect(inputs).toHaveLength(1);
  });

  it("shows the completed static timeline without a viewport race", () => {
    render(<PipelineComparison />);
    expect(screen.getByText("12 / 12 steps")).toBeInTheDocument();
    expect(screen.getByText("Complete")).toBeInTheDocument();
  });

  it("applies a tokenized scroll mask only after the trace has more than seven visible steps", () => {
    const { rerender } = render(
      <PipelineComparisonExecutionPanel elapsed={6} steps={MASK_TEST_STEPS} />,
    );
    const scrollRegion = screen.getByTestId("pipeline-comparison-trace-scroll");

    expect(scrollRegion).toHaveAttribute("role", "region");
    expect(scrollRegion).toHaveAccessibleName(
      "Representative adaptive evidence trace",
    );
    expect(scrollRegion).toHaveAttribute("tabindex", "0");
    expect(scrollRegion.style.maskImage).toBe("");

    rerender(
      <PipelineComparisonExecutionPanel elapsed={7} steps={MASK_TEST_STEPS} />,
    );

    expect(scrollRegion.style.maskImage).toContain(
      "var(--brand-ink, #0B1F24) 10%",
    );
    expect(scrollRegion.style.maskImage).not.toContain("#0B1F24 10%");
    expect(scrollRegion.style.maskImage).not.toContain("black 10%");
  });

  it("presents the adaptive timeline and metrics together", () => {
    render(<PipelineComparison />);
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getByText("12 / 12 steps")).toBeInTheDocument();
  });

  it("shows timeline metrics after completion", () => {
    render(<PipelineComparison />);
    expect(screen.getByText("Intake")).toBeInTheDocument();
    expect(screen.getByText("Evidence Gap")).toBeInTheDocument();
    expect(screen.getByText("Escalation")).toBeInTheDocument();
    expect(screen.getByText("Handoff")).toBeInTheDocument();
  });

  it("does not schedule timeline playback for reduced-motion users", () => {
    mockReducedMotion = true;
    const setIntervalSpy = vi.spyOn(global, "setInterval");

    render(<PipelineComparison />);

    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getByText("12 / 12 steps")).toBeInTheDocument();
    expect(screen.getByText("Intake")).toBeInTheDocument();
    expect(setIntervalSpy).not.toHaveBeenCalled();

    setIntervalSpy.mockRestore();
  });

  it("shows use-case guidance after completion", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(/Lean when evidence is sufficient/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Escalated when the record demands it/),
    ).toBeInTheDocument();
  });

  it("shows governed-path banner after completion", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(/escalation is recorded only when evidence requires it/),
    ).toBeInTheDocument();
  });

  it("does not expose public race controls or mode labels", () => {
    render(<PipelineComparison />);
    expect(screen.queryByText("Replay")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence Intake")).not.toBeInTheDocument();
    expect(screen.queryByText("Adaptive Review")).not.toBeInTheDocument();
  });

  it("does not show reasoning theater", () => {
    render(<PipelineComparison />);
    expect(screen.queryByText("reasoning")).not.toBeInTheDocument();
  });

  it("shows governed escalation messages without function-call theater", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(/Specification excerpts attached/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/fetch_specification/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/search_spec_definitions/),
    ).not.toBeInTheDocument();
  });

  it("shows element statuses with correct risk badges", () => {
    render(<PipelineComparison />);
    const mediumRiskBadges = screen.getAllByText("medium");
    expect(mediumRiskBadges).toHaveLength(1);
  });

  it("keeps the evidence story visible without relying on intersection state", () => {
    render(<PipelineComparison />);
    expect(
      screen.getByText(/Compound \+ patent claims received/),
    ).toBeInTheDocument();
    expect(screen.getByText("Intake")).toBeInTheDocument();
    expect(screen.getByText("Handoff")).toBeInTheDocument();
  });

  it("never schedules autoplay", () => {
    const setIntervalSpy = vi.spyOn(global, "setInterval");
    render(<PipelineComparison />);
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });
});
