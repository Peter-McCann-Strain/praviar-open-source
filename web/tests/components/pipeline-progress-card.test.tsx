import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { PipelineProgressCard } from "@/components/analysis-detail/pipeline-progress-card";
import type { PipelineStep } from "@/stores/pipeline-store";

vi.mock("@/components/pipeline/live-results-feed", () => ({
  LiveResultsFeed: ({
    title,
    results,
  }: {
    title: string;
    results: Array<{ label: string }>;
  }) => (
    <div data-testid="live-results-feed">
      <span>{title}</span>
      {results.map((result) => (
        <span key={result.label}>{result.label}</span>
      ))}
    </div>
  ),
}));

vi.mock("@/components/report/report-skeleton", () => ({
  ReportSkeleton: () => <div data-testid="report-skeleton" />,
}));

function makeSteps(): PipelineStep[] {
  return [
    {
      number: 1,
      name: "Resolve Compound",
      status: "completed",
      startedAt: "2026-04-12T10:00:00Z",
      completedAt: "2026-04-12T10:00:20Z",
    },
    {
      number: 2,
      name: "Search Prior Art",
      status: "completed",
      startedAt: "2026-04-12T10:00:20Z",
      completedAt: "2026-04-12T10:01:20Z",
    },
    {
      number: 3,
      name: "Triage Results",
      status: "running",
      startedAt: "2026-04-12T10:01:20Z",
    },
    { number: 4, name: "Analyze Patents", status: "pending" },
    { number: 5, name: "DoE", status: "pending" },
    { number: 6, name: "Invalidity", status: "pending" },
    { number: 7, name: "Verify", status: "pending" },
    { number: 8, name: "Report", status: "pending" },
  ];
}

describe("PipelineProgressCard", () => {
  it("renders step rows and progress summary", () => {
    render(
      <PipelineProgressCard
        currentStep={3}
        elapsedMs={90_000}
        hasLiveData={false}
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPayloads={{}}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByTestId("pipeline-progress-card-content")).toHaveClass(
      "p-4",
      "sm:p-6",
      "lg:p-8",
    );
    expect(screen.getByText("Step 3: Triaging Patents")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "Pipeline progress" }),
    ).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText(/step 3 of 8/i)).toBeInTheDocument();
    expect(
      screen.getByTestId("pipeline-execution-disclosure"),
    ).toBeInTheDocument();
    expect(screen.getByText("8-stage execution receipt")).toBeInTheDocument();
  });

  it("uses mobile-safe step rows without truncating live legal context", () => {
    render(
      <PipelineProgressCard
        currentStep={3}
        elapsedMs={30_000}
        hasLiveData
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPayloads={{
          3: { message: "Triage in progress", relevant: 4, total: 12 },
        }}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByTestId("pipeline-progress-step-3")).toHaveClass(
      "grid",
      "grid-cols-[2.5rem_minmax(0,1fr)]",
      "sm:flex",
    );
    expect(
      screen.getByText("4 of 12 patents passed relevance triage"),
    ).toHaveClass("leading-5", "[overflow-wrap:anywhere]");
    expect(
      screen.getByText("4 of 12 patents passed relevance triage"),
    ).not.toHaveClass("truncate");
    expect(screen.getByText("Running...")).toHaveClass(
      "col-start-2",
      "sm:flex-shrink-0",
    );
  });

  it("renders live feed items and report preview when report generation is running", () => {
    render(
      <PipelineProgressCard
        currentStep={8}
        elapsedMs={120_000}
        hasLiveData={false}
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPct={87.5}
        progressPayloads={{
          2: { message: "Search complete", patents_found: 24 },
          3: { message: "Triage complete", relevant: 6, total: 24 },
          4: {
            message: "Analysis underway",
            current_patent: "US123",
            analyzed: 2,
            total: 6,
          },
        }}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByTestId("live-results-feed")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "Pipeline progress" }),
    ).toHaveAttribute("aria-valuenow", "88");
    expect(
      screen.getByText("Pipeline 88% complete · step 8 of 8"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/100% complete/i)).not.toBeInTheDocument();
    expect(screen.getByText("24 patents discovered")).toBeInTheDocument();
    expect(screen.getByText("6 patents relevant")).toBeInTheDocument();
    expect(screen.getByText("US123")).toBeInTheDocument();
    expect(screen.getByTestId("report-skeleton")).toBeInTheDocument();
  });

  it("keeps zero-result milestones visible because they are meaningful outcomes", () => {
    render(
      <PipelineProgressCard
        currentStep={3}
        elapsedMs={45_000}
        hasLiveData={false}
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPayloads={{
          2: { message: "Search completed", patents_found: 0 },
          3: { message: "No relevant patents", relevant: 0, total: 0 },
        }}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByText("0 patents discovered")).toBeInTheDocument();
    expect(screen.getByText("0 patents relevant")).toBeInTheDocument();
  });

  it("renders live step state from the pipeline stream when available", () => {
    render(
      <PipelineProgressCard
        currentStep={3}
        elapsedMs={30_000}
        hasLiveData
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPayloads={{
          3: { message: "Triage in progress", relevant: 4, total: 12 },
        }}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByText("Running...")).toBeInTheDocument();
    expect(
      screen.getByText("4 of 12 patents passed relevance triage"),
    ).toBeInTheDocument();
  });

  it("does not leak undefined for partial live payloads", () => {
    const { container } = render(
      <PipelineProgressCard
        currentStep={4}
        elapsedMs={60_000}
        hasLiveData
        isComplete={false}
        isFailed={false}
        isRunning
        pipelineIsComplete={false}
        progressPayloads={{
          3: { relevant: 4 },
          4: { analyzed: 2, current_patent: "US123" },
        }}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByText("4 patents relevant")).toBeInTheDocument();
    expect(screen.getByText("US123")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("undefined");
  });

  it("renders queued copy instead of step zero for pending records", () => {
    render(
      <PipelineProgressCard
        currentStep={0}
        elapsedMs={0}
        hasLiveData={false}
        isComplete={false}
        isFailed={false}
        isRunning={false}
        pipelineIsComplete={false}
        progressPayloads={{}}
        steps={makeSteps()}
      />,
    );

    expect(screen.getByText("Pipeline queued")).toBeInTheDocument();
    expect(screen.queryByText(/Step 0 of 8/i)).not.toBeInTheDocument();
  });

  it("clamps out-of-range step progress to the known pipeline length", () => {
    render(
      <PipelineProgressCard
        currentStep={9}
        elapsedMs={0}
        hasLiveData={false}
        isComplete={false}
        isFailed={false}
        isRunning={false}
        pipelineIsComplete={false}
        progressPayloads={{}}
        steps={makeSteps()}
      />,
    );

    expect(
      screen.getByRole("progressbar", { name: "Pipeline progress" }),
    ).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText(/Step 8 of 8/i)).toBeInTheDocument();
  });

  it("distinguishes a closed workflow stage from missing invalidity coverage", () => {
    render(
      <PipelineProgressCard
        currentStep={8}
        elapsedMs={0}
        hasLiveData={false}
        invalidityAssessmentsCount={0}
        isComplete
        isFailed={false}
        isRunning={false}
        pipelineIsComplete={false}
        progressPayloads={{}}
        steps={makeSteps()}
      />,
    );

    expect(
      screen.getByText("Invalidity workflow closed without assessment output"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-progress-step-6")).toHaveTextContent(
      "workflow closed without assessment output",
    );
    expect(screen.getByTestId("pipeline-progress-step-6")).toHaveTextContent(
      "No output",
    );
    expect(screen.getByText(/validity remains unknown/i)).toBeInTheDocument();
  });
});
