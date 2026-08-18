import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfigurationAnalysisParameters } from "@/components/analysis-wizard/configuration-analysis-parameters";
import type { ConfigState } from "@/stores/config-store";

function createConfig(): ConfigState {
  return {
    maxAnalysisPatents: 20,
    maxDoeCandidates: 15,
    triageBatchSize: 10,
    analysisThinkingBudget: 12000,
    thinkingEffortAnalysis: "high",
    thinkingEffortTriage: "medium",
    thinkingEffortReport: "high",
    setConfig: vi.fn(),
  } as unknown as ConfigState;
}

describe("ConfigurationAnalysisParameters", () => {
  it("keeps slider bounds aligned with frontend and API validation", () => {
    render(<ConfigurationAnalysisParameters config={createConfig()} />);

    expect(screen.getByLabelText("Patent Review Limit")).toHaveAttribute(
      "max",
      "30",
    );
    expect(screen.getByLabelText("DoE Candidate Limit")).toHaveAttribute(
      "max",
      "20",
    );
    expect(screen.getByLabelText("Triage Batch Size")).toHaveAttribute(
      "max",
      "15",
    );
  });
});
