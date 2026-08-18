import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RunningAnalysisWorkspace } from "@/components/analysis-detail/running-analysis-workspace";
import type { PipelineStep } from "@/stores/pipeline-store";

const steps: PipelineStep[] = [
  {
    number: 1,
    name: "resolve",
    status: "completed",
    startedAt: "2026-06-20T10:00:00Z",
    completedAt: "2026-06-20T10:00:05Z",
  },
  {
    number: 2,
    name: "search",
    status: "completed",
    startedAt: "2026-06-20T10:00:05Z",
    completedAt: "2026-06-20T10:02:00Z",
  },
  {
    number: 3,
    name: "triage",
    status: "running",
    description: "Claim family triage is running",
    startedAt: "2026-06-20T10:02:00Z",
  },
  { number: 4, name: "analyze", status: "pending" },
  { number: 5, name: "doe", status: "pending" },
  { number: 6, name: "invalidity", status: "pending" },
  { number: 7, name: "verify", status: "pending" },
  { number: 8, name: "report", status: "pending" },
];

describe("RunningAnalysisWorkspace", () => {
  it("renders live audit-trail context for an in-flight analysis", () => {
    render(
      <RunningAnalysisWorkspace
        currentStep={3}
        elapsedMs={185_000}
        hasCheckpoint={false}
        hasLiveData
        progressPayloads={{
          2: { patents_found: 128, message: "Search complete" },
          3: { relevant: 17, total: 128, message: "Triage underway" },
          4: { analyzed: 2, total: 17, current_patent: "US202600142" },
        }}
        steps={steps}
      />,
    );

    expect(screen.getByTestId("live-evidence-dossier")).toHaveClass(
      "praviar-live-dossier-field",
    );
    expect(
      screen.getByRole("heading", { name: "Audit trail in progress" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Live evidence dossier")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Synthetic research preview; not a legal clearance opinion.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Triaging Patents")).toBeInTheDocument();
    expect(screen.getByText("3:05")).toBeInTheDocument();
    expect(screen.getByText("Live stream connected")).toBeInTheDocument();
    expect(screen.getByText("What changed since launch")).toBeInTheDocument();
    expect(
      screen.getByText("128 patent records discovered"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("17 relevant families surfaced"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("US202600142 claim packet active"),
    ).toBeInTheDocument();
    expect(screen.getByText("Now assembling")).toBeInTheDocument();
    expect(
      screen.getAllByText("Reviewer-ready claim packet").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("Patent analyses")).toBeInTheDocument();
    expect(screen.queryByText("Claims analyzed")).not.toBeInTheDocument();
    expect(screen.getByText("US202600142")).toBeInTheDocument();
    expect(screen.getByText("Legal output remains draft")).toBeInTheDocument();
  });

  it("uses backend progress for report generation without implying completion", () => {
    render(
      <RunningAnalysisWorkspace
        currentStep={8}
        elapsedMs={480_000}
        hasCheckpoint={false}
        hasLiveData
        progressPct={87.5}
        progressPayloads={{
          8: { format: "PDF" },
        }}
        steps={[
          ...steps
            .slice(0, 7)
            .map((step) => ({ ...step, status: "completed" as const })),
          { number: 8, name: "report", status: "running" },
        ]}
      />,
    );

    expect(
      screen.getByRole("progressbar", { name: "Live dossier progress" }),
    ).toHaveAttribute("aria-valuenow", "88");
    expect(screen.queryByText(/100% complete/i)).not.toBeInTheDocument();
    expect(
      screen.getAllByText("Interactive FTO report").length,
    ).toBeGreaterThan(0);
  });

  it("shows attention state when the pipeline stream has an issue", () => {
    render(
      <RunningAnalysisWorkspace
        currentStep={4}
        elapsedMs={240_000}
        hasCheckpoint={false}
        hasLiveData={false}
        hasPipelineIssue
        progressPayloads={{}}
        steps={steps}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Stream needs attention")).toBeInTheDocument();
    expect(screen.queryByText("On track")).not.toBeInTheDocument();
    expect(screen.queryByText("Live stream connected")).not.toBeInTheDocument();
  });

  it("shows review pause state without implying a pipeline failure", () => {
    render(
      <RunningAnalysisWorkspace
        currentStep={4}
        elapsedMs={240_000}
        hasCheckpoint
        hasLiveData={false}
        progressPayloads={{}}
        steps={steps}
      />,
    );

    expect(screen.getByText("Review paused")).toBeInTheDocument();
    expect(screen.getByText("What changed since launch")).toBeInTheDocument();
    expect(
      screen.getByText(/The first source event has not arrived yet/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Pipeline Error/i)).not.toBeInTheDocument();
  });
});
